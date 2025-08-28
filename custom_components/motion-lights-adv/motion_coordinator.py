"""Motion-activated lights coordinator for Motion Lights Advanced integration."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timedelta
import logging
import time
from typing import Any

from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BRIGHTNESS_DAY,
    CONF_BRIGHTNESS_NIGHT,
    CONF_BACKGROUND_LIGHT,
    CONF_FEATURE_LIGHT,
    CONF_CEILING_LIGHT,
    CONF_DARK_OUTSIDE,
    CONF_EXTENDED_TIMEOUT,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
    DEFAULT_EXTENDED_TIMEOUT,
    DEFAULT_MOTION_ACTIVATION,
    DEFAULT_NO_MOTION_WAIT,
    DOMAIN,
    # States
    STATE_OVERRIDDEN,
    STATE_IDLE,
    STATE_MOTION_AUTO,
    STATE_MOTION_MANUAL,
    STATE_AUTO,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
)

# State definitions are imported from const.py

# Timer types
TIMER_MOTION = "motion"  # 120s default when motion=OFF and lights ON
TIMER_EXTENDED = "extended"  # 600s default for manual intervention

_LOGGER = logging.getLogger(__name__)


class MotionLightsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for motion-activated lights logic per tight specification."""

    def __init__(self, hass: HomeAssistant, config_entry) -> None:
        """Initialize the motion coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_motion",
            update_interval=None,  # Event-driven
            config_entry=config_entry,
        )

        self.config_entry = config_entry
        self.data = {}

        # Load light entities from configuration
        self._load_config()

        # State management per specification
        self._current_state = STATE_IDLE

        # Timer management - only one active at a time
        self._active_timer: asyncio.TimerHandle | None = None
        self._timer_type: str | None = None  # TIMER_MOTION or TIMER_EXTENDED
        self._timer_end_time: dt_util.dt.datetime | None = None

        # Manual threshold for detecting user intervention (2% brightness delta)
        self._brightness_manual_threshold_pct: int = 2

        # Track recent service call contexts to identify integration-originated changes
        self._recent_context_ids: set[str] = set()
        self._context_queue: deque[tuple[str, float]] = deque()
        self._max_context_age_seconds: int = 15

        # Motion statistics and diagnostics
        self._last_motion_time: datetime | None = None
        self._last_manual_reason: str | None = None
        self._event_log: deque[tuple[datetime, str]] = deque(maxlen=25)

        # Timer durations (seconds)
        self._motion_timer_duration = self._no_motion_wait  # Default 120s
        self._extended_timer_duration = (
            self.extended_timeout
        )  # Default 600s for manual intervention

        # Light state tracking
        self._tracked_lights: dict[str, dict[str, Any]] = {}
        self._unsubscribers: list[callable] = []

    def _load_config(self) -> None:
        """Load entities from config entry and normalize to lists with fallbacks."""
        data = self.config_entry.data

        def _as_list(value: Any) -> list[str]:
            """Return value as a list of strings (entity ids)."""
            if value is None:
                return []
            if isinstance(value, str):  # Single entity id provided
                return [value]
            if isinstance(value, (list, tuple, set)):
                return [str(v) for v in value]
            _LOGGER.warning(
                "Unexpected light config value type %s: %s", type(value), value
            )
            return []

        # Motion activation setting
        self.motion_activation = data.get(
            CONF_MOTION_ACTIVATION, DEFAULT_MOTION_ACTIVATION
        )

        # No motion wait time
        self._no_motion_wait = data.get(CONF_NO_MOTION_WAIT, DEFAULT_NO_MOTION_WAIT)

        self.extended_timeout = data.get(
            CONF_EXTENDED_TIMEOUT, DEFAULT_EXTENDED_TIMEOUT
        )

        # Motion sensors and override switch (optional)
        self.motion_entities = _as_list(data.get(CONF_MOTION_ENTITY))
        # Normalize override switch: accept a single entity_id; if a list was provided, pick the first
        override_cfg = data.get(CONF_OVERRIDE_SWITCH)
        if isinstance(override_cfg, (list, tuple, set)):
            override_list = [str(v) for v in override_cfg if v]
            self.override_switch = override_list[0] if override_list else None
        else:
            self.override_switch = str(override_cfg) if override_cfg else None

        # Optional dark-outside switch/sensor for night detection
        self.dark_outside = data.get(CONF_DARK_OUTSIDE)

        # Brightness settings
        self.brightness_day = data.get(CONF_BRIGHTNESS_DAY, 60)
        self.brightness_night = data.get(CONF_BRIGHTNESS_NIGHT, 10)

        # Separate light entities (lists)
        self.background_lights = _as_list(data.get(CONF_BACKGROUND_LIGHT))
        self.feature_lights = _as_list(data.get(CONF_FEATURE_LIGHT))
        self.ceiling_lights = _as_list(data.get(CONF_CEILING_LIGHT))

        # Backwards-compatible single-entity fallbacks
        self.motion_entity = self.motion_entities[0] if self.motion_entities else ""
        self.background_light = (
            self.background_lights[0] if self.background_lights else ""
        )
        self.feature_light = self.feature_lights[0] if self.feature_lights else ""
        self.ceiling_light = self.ceiling_lights[0] if self.ceiling_lights else ""

        # Warn if any light does not look like a light entity
        for light_name, light_entities in [
            ("background_light", self.background_lights),
            ("feature_light", self.feature_lights),
            ("ceiling_light", self.ceiling_lights),
        ]:
            for light_entity in light_entities:
                if not light_entity.startswith("light."):
                    _LOGGER.debug(
                        "Configured entity %s=%s does not start with 'light.' - verify it is a light entity",
                        light_name,
                        light_entity,
                    )

        _LOGGER.debug(
            "Loaded config: motion=%s, override=%s, dark_outside=%s, motion_activation=%s, background_lights=%s, feature_lights=%s, ceiling_lights=%s",
            self.motion_entities,
            self.override_switch,
            self.dark_outside,
            self.motion_activation,
            self.background_lights,
            self.feature_lights,
            self.ceiling_lights,
        )

    async def async_setup_listeners(self) -> None:
        """Set up event listeners."""
        # Proceed even if some lists are empty; features will degrade gracefully

        # Check if light entities are available, retry if needed
        await self._ensure_entities_available()

        # Set up motion sensor monitoring (if configured)
        if self.motion_entities:
            self._setup_motion_monitoring()

        # Set up override switch monitoring (if configured)
        if self.override_switch:
            self._setup_override_monitoring()

        # Set up light monitoring
        self._setup_light_monitoring()

        # Capture initial state
        self._capture_initial_light_states()

        # Set initial state based on current conditions
        self._set_initial_state()
        # Publish initial data so sensors have content immediately
        self._update_light_data()

    async def _ensure_entities_available(self) -> None:
        """Ensure all configured entities are available, retry if needed."""
        max_retries = 5
        retry_delay = 2  # seconds

        for attempt in range(max_retries):
            missing_entities = [
                ent for ent in self.motion_entities if not self.hass.states.get(ent)
            ]

            # Check override switch (if configured)
            if self.override_switch:
                if isinstance(self.override_switch, (list, tuple, set)):
                    missing_entities.extend(
                        [
                            ov
                            for ov in self.override_switch
                            if not self.hass.states.get(ov)
                        ]
                    )
                elif not self.hass.states.get(self.override_switch):
                    missing_entities.append(self.override_switch)

            # Check all lights
            missing_entities.extend(
                [
                    lid
                    for lid in self._all_configured_lights()
                    if not self.hass.states.get(lid)
                ]
            )

            if not missing_entities:
                _LOGGER.info("All entities available for motion lights integration")
                return

            _LOGGER.warning(
                "Attempt %d/%d: Missing entities: %s - retrying in %ds",
                attempt + 1,
                max_retries,
                missing_entities,
                retry_delay,
            )

            if attempt < max_retries - 1:  # Don't wait after last attempt
                await asyncio.sleep(retry_delay)

        _LOGGER.error(
            "Some entities still missing after %d attempts: %s",
            max_retries,
            missing_entities,
        )

    def _set_initial_state(self) -> None:
        """Set initial state based on current conditions per specification."""
        if self._is_override_active():
            self._current_state = STATE_OVERRIDDEN
            _LOGGER.debug("Initial state: OVERRIDDEN (override active)")
        elif self._any_configured_lights_on():
            self._current_state = STATE_MANUAL
            if not self.motion_activation:
                self._last_manual_reason = (
                    "lights on at startup (motion activation disabled)"
                )
                # Start extended timer immediately for energy saving
                self._start_timer(TIMER_EXTENDED)
                _LOGGER.debug(
                    "Initial state: MANUAL with timer (motion activation disabled)"
                )
            else:
                self._last_manual_reason = "lights on at startup"
                _LOGGER.debug("Initial state: MANUAL (lights on at startup)")
        else:
            self._current_state = STATE_IDLE
            _LOGGER.debug("Initial state: IDLE (no lights on)")

    def _setup_motion_monitoring(self) -> None:
        """Set up motion sensor monitoring."""
        if not self.motion_entities:
            _LOGGER.info("No motion sensors configured; skipping motion monitoring")
            return

        missing = [e for e in self.motion_entities if not self.hass.states.get(e)]
        if missing:
            _LOGGER.warning("Some motion sensors not found: %s", missing)

        self._unsubscribers.append(
            async_track_state_change_event(
                self.hass,
                list(self.motion_entities),
                self._async_motion_state_changed,
            )
        )
        _LOGGER.info("Monitoring motion sensors: %s", self.motion_entities)

    @callback
    def _async_motion_state_changed(self, event: Event) -> None:
        """Handle motion sensor state changes per tight specification."""
        new_state = event.data.get("new_state")

        if not new_state:
            return

        if new_state.state == "on":
            # Motion ON
            self._handle_motion_on()
        elif new_state.state == "off":
            # Motion OFF for one sensor; only treat as OFF if all are off
            any_on = False
            for ent in self.motion_entities:
                st = self.hass.states.get(ent)
                if st is not None and st.state == "on":
                    any_on = True
                    break
            if not any_on:
                self._handle_motion_off()

        # Update coordinator data
        self._update_light_data()

    def _handle_motion_on(self) -> None:
        """Handle motion=ON per specification."""
        self._last_motion_time = dt_util.now()
        self._record_event("motion_on")

        _LOGGER.info("Motion ON")

        # Check if override is active - ignore everything per specification
        if self._current_state == STATE_OVERRIDDEN:
            _LOGGER.debug("Override active - ignoring motion detection")
            self._record_event("motion_ignored_override_active")
            return

        # Check if manual-off override is active
        if self._current_state == STATE_MANUAL_OFF:
            _LOGGER.debug("Manual-off override active - ignoring motion detection")
            self._record_event("motion_ignored_manual_off")
            return

        # Check if motion activation is disabled
        if not self.motion_activation:
            _LOGGER.debug("Motion activation disabled - treating any lights as manual")
            if self._any_configured_lights_on():
                # Any lights on → MANUAL state
                self._cancel_active_timer()
                self._current_state = STATE_MANUAL
                self._last_manual_reason = (
                    "motion activation disabled, lights treated as manual"
                )
                _LOGGER.debug("Motion activation OFF + lights ON → MANUAL")
                self._record_event("motion_disabled_to_manual")
            else:
                # No lights on → stay in current state, no automatic activation
                _LOGGER.debug("Motion activation OFF + no lights → no action")
                self._record_event("motion_disabled_no_action")
            return

        if self._current_state == STATE_MANUAL:
            # If MANUAL → cancel ExtendedTimer (if any) → MOTION-MANUAL (don't change lights)
            self._cancel_active_timer()
            self._current_state = STATE_MOTION_MANUAL
            _LOGGER.debug("MANUAL → MOTION-MANUAL (no light changes)")
            self._record_event("manual_to_motion_manual")
        else:
            # Else (IDLE/AUTO) → turn on TOD-target lights at configured brightness → MOTION-AUTO
            self._cancel_active_timer()
            self._current_state = STATE_MOTION_AUTO
            self.hass.async_create_task(self._async_turn_on_tod_lights())
            _LOGGER.debug("→ MOTION-AUTO (turning on lights)")
            self._record_event("motion_auto_activating_lights")

    def _handle_motion_off(self) -> None:
        """Handle motion=OFF per specification."""
        self._record_event("motion_off")
        _LOGGER.info("Motion OFF")

        # Check if override is active - ignore everything per specification
        if self._current_state == STATE_OVERRIDDEN:
            _LOGGER.debug("Override active - ignoring motion OFF")
            self._record_event("motion_off_ignored_override_active")
            return

        # If manual-off override is active, keep it; do not change timers/state
        if self._current_state == STATE_MANUAL_OFF:
            _LOGGER.debug("Manual-off override active - ignoring motion OFF")
            self._record_event("motion_off_ignored_manual_off")
            return

        # Check if motion activation is disabled
        if not self.motion_activation:
            _LOGGER.debug(
                "Motion activation disabled - automatic turn-on disabled, but turn-off timers still active"
            )
            # With motion activation disabled, we don't automatically turn lights ON
            # but we still turn them OFF after timeout to save energy
            if self._any_configured_lights_on():
                self._current_state = STATE_MANUAL
                self._last_manual_reason = (
                    "motion activation disabled, but will turn off after timeout"
                )
                # Start extended timer for manual lights (even with motion activation disabled)
                self._start_timer(TIMER_EXTENDED)
                _LOGGER.debug(
                    "Motion activation OFF + lights ON → MANUAL with turn-off timer"
                )
                self._record_event("motion_off_disabled_manual_with_timer")
            else:
                self._current_state = STATE_IDLE
                _LOGGER.debug("Motion activation OFF + no lights → IDLE")
                self._record_event("motion_off_disabled_idle")
            return

        # Motion OFF logic depends on current state and lights
        lights_on = self._any_configured_lights_on()
        if self._current_state == STATE_MOTION_MANUAL:
            if lights_on:
                self._current_state = STATE_MANUAL
                self._start_timer(TIMER_EXTENDED)
                _LOGGER.debug("MOTION-MANUAL → MANUAL + ExtendedTimer")
                self._record_event("motion_manual_to_manual")
            else:
                self._current_state = STATE_IDLE
                _LOGGER.debug("MOTION-MANUAL + no lights → IDLE")
                self._record_event("motion_manual_to_idle")
        elif self._current_state == STATE_MANUAL and lights_on:
            # MANUAL (no motion) and lights on → keep MANUAL and ensure ExtendedTimer
            self._start_timer(TIMER_EXTENDED)
            _LOGGER.debug("MANUAL + lights ON → ExtendedTimer → stay MANUAL")
            self._record_event("manual_extended_timer")
        elif lights_on:
            # Any other state with lights on → AUTO with MotionTimer
            self._start_timer(TIMER_MOTION)
            self._current_state = STATE_AUTO
            _LOGGER.debug("Lights ON → MotionTimer → AUTO")
            self._record_event("motion_to_auto")
        else:
            # No lights → IDLE
            self._current_state = STATE_IDLE
            _LOGGER.debug("No lights ON → IDLE")
            self._record_event("motion_to_idle")

    async def _async_turn_on_tod_lights(self) -> None:
        """Turn on time-of-day target lights at configured brightness."""
        lights_to_turn_on, target_brightness = self._determine_lights_and_brightness()

        if not lights_to_turn_on:
            _LOGGER.info("No lights configured for time-of-day activation")
            return

        _LOGGER.info(
            "Turning on %d TOD lights at %d%% brightness: %s",
            len(lights_to_turn_on),
            target_brightness,
            lights_to_turn_on,
        )

        for light in lights_to_turn_on:
            current_state = self.hass.states.get(light)
            if current_state is None:
                _LOGGER.debug("Skipping %s - entity not found", light)
                continue

            if current_state.state == "off":
                await self._async_set_light_state(light, "on", target_brightness)
                _LOGGER.debug("Turned on %s at %d%%", light, target_brightness)
            else:
                _LOGGER.debug("Leaving %s unchanged (already on)", light)

    def _cancel_active_timer(self) -> None:
        """Cancel any active timer."""
        if self._active_timer:
            _LOGGER.debug("Cancelling %s timer", self._timer_type)
            self._active_timer.cancel()
            self._active_timer = None
            self._timer_type = None
            self._timer_end_time = None
            self._record_event(f"cancel_{self._timer_type or 'unknown'}_timer")

    def _start_timer(self, timer_type: str) -> None:
        """Start a timer of the specified type."""
        self._cancel_active_timer()

        if timer_type == TIMER_MOTION:
            duration = self._motion_timer_duration
        elif timer_type == TIMER_EXTENDED:
            duration = self._extended_timer_duration
        else:
            _LOGGER.error("Unknown timer type: %s", timer_type)
            return

        self._timer_type = timer_type
        self._timer_end_time = dt_util.now() + timedelta(seconds=duration)

        _LOGGER.debug("Starting %s timer for %ds", timer_type, duration)
        self._active_timer = self.hass.loop.call_later(
            duration,
            lambda: self.hass.async_create_task(self._async_timer_expired(timer_type)),
        )
        self._record_event(f"start_{timer_type}_timer")

    async def _async_timer_expired(self, timer_type: str) -> None:
        """Handle timer expiration."""
        # Verify this is still the active timer
        if self._timer_type != timer_type:
            _LOGGER.debug("Ignoring expired %s timer (not active)", timer_type)
            return

        _LOGGER.info("%s timer expired", timer_type.title())
        self._record_event(f"{timer_type}_timer_expired")

        # Clear timer state
        self._active_timer = None
        self._timer_type = None
        self._timer_end_time = None

        # Timer end → turn off all configured lights that are ON → IDLE
        await self._async_turn_off_configured_lights()
        self._current_state = STATE_IDLE
        _LOGGER.debug("Timer end → lights OFF → IDLE")
        self._record_event("timer_to_idle")

        # Update coordinator data
        self._update_light_data()

    async def _async_turn_off_configured_lights(self) -> None:
        """Turn off all configured lights that are currently on."""
        for light in self._all_configured_lights():
            current_state = self.hass.states.get(light)
            if current_state and current_state.state == "on":
                await self._async_set_light_state(light, "off", 0)
                _LOGGER.info("Turned off light: %s", light)
            else:
                _LOGGER.debug("Light %s was already off", light)

    def _setup_override_monitoring(self) -> None:
        """Set up override switch monitoring."""
        override_state = self.hass.states.get(self.override_switch)
        if not override_state:
            _LOGGER.warning(
                "Override switch entity '%s' not found", self.override_switch
            )
            return

        self._unsubscribers.append(
            async_track_state_change_event(
                self.hass,
                [self.override_switch],
                self._async_override_state_changed,
            )
        )
        _LOGGER.info("Monitoring override switch: %s", self.override_switch)

    @callback
    def _async_override_state_changed(self, event: Event) -> None:
        """Handle override switch state changes per specification."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if not new_state or not old_state:
            return

        if new_state.state == "on" and old_state.state == "off":
            # Override ON → cancel timers → OVERRIDDEN
            _LOGGER.info("Override switch ON → cancel timers → OVERRIDDEN")
            self._cancel_active_timer()
            self._current_state = STATE_OVERRIDDEN
            self._record_event("override_on")
        elif new_state.state == "off" and old_state.state == "on":
            # Override OFF → evaluate state based on lights
            _LOGGER.info("Override switch OFF → evaluating state")
            self._handle_override_off()
            self._record_event("override_off")

        # Update coordinator data
        self._update_light_data()

    def _handle_override_off(self) -> None:
        """Handle override=OFF per specification."""
        if self._any_configured_lights_on():
            # If any light ON → MANUAL with extended timer for auto turn-off
            self._current_state = STATE_MANUAL
            self._last_manual_reason = "override off with lights on"
            self._start_timer(TIMER_EXTENDED)
            _LOGGER.debug("Override OFF + lights ON → MANUAL with timer")
            self._record_event("override_off_to_manual_with_timer")
        else:
            # Else → IDLE
            self._current_state = STATE_IDLE
            _LOGGER.debug("Override OFF + no lights → IDLE")
            self._record_event("override_off_to_idle")

    def _setup_light_monitoring(self) -> None:
        """Set up light monitoring to track state changes."""
        lights = self._all_configured_lights()
        if not lights:
            _LOGGER.warning("No lights configured; skipping light monitoring")
            return
        self._unsubscribers.append(
            async_track_state_change_event(
                self.hass,
                lights,
                self._async_light_state_changed,
            )
        )
        _LOGGER.info("Tracking lights for state changes: %s", lights)

    @callback
    def _async_light_state_changed(self, event: Event) -> None:
        """Handle light state changes per specification."""
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if not new_state or not old_state:
            return

        # Determine whether this change originated from our integration
        integration_origin = self._is_integration_context(new_state.context)

        # Calculate brightness changes
        old_brightness = self._get_brightness_percent(old_state)
        new_brightness = self._get_brightness_percent(new_state)
        brightness_diff = abs(new_brightness - old_brightness)

        # Update tracking
        self._tracked_lights[entity_id] = {
            "state": new_state.state,
            "brightness": new_brightness,
            "last_changed": dt_util.now(),
            "integration_origin": integration_origin,
        }

        # Log significant changes
        significant_change = new_state.state != old_state.state or brightness_diff > 0
        if significant_change:
            _LOGGER.info(
                "Light %s changed: %s@%d%% → %s@%d%% (our_context=%s)",
                entity_id,
                old_state.state,
                old_brightness,
                new_state.state,
                new_brightness,
                integration_origin,
            )

        # Handle external light changes per specification
        if not integration_origin:
            self._handle_external_light_change(
                entity_id, old_state, new_state, brightness_diff
            )

        # Check if no configured lights are ON → cancel timers → IDLE (unless overridden or manual-off)
        if not self._any_configured_lights_on() and self._current_state not in (
            STATE_OVERRIDDEN,
            STATE_MANUAL_OFF,
        ):
            self._cancel_active_timer()
            self._current_state = STATE_IDLE
            _LOGGER.debug("No configured lights ON → cancel timers → IDLE")
            self._record_event("no_lights_to_idle")

        # Update coordinator data
        self._update_light_data()

    def _handle_external_light_change(
        self, entity_id: str, old_state, new_state, brightness_diff: int
    ) -> None:
        """Handle external (non-integration) light changes per specification."""
        # External light change (not our context):

        # If override is active, ignore external light c    hanges per specification
        if self._current_state == STATE_OVERRIDDEN:
            _LOGGER.debug(
                "Override active - ignoring external light change for %s", entity_id
            )
            self._record_event(f"light_change_ignored_override:{entity_id}")
            return

        # If motion activation is disabled, treat all light changes as manual
        if not self.motion_activation:
            if new_state.state == "on" and old_state.state == "off":
                self._current_state = STATE_MANUAL
                self._last_manual_reason = (
                    f"light turned on (motion activation disabled): {entity_id}"
                )
                # Start extended timer immediately for energy saving
                self._start_timer(TIMER_EXTENDED)
                _LOGGER.debug(
                    "Motion activation OFF → light turned ON → MANUAL with timer"
                )
                self._record_event(f"motion_disabled_manual_with_timer:{entity_id}")
            elif (
                new_state.state == "on"
                and brightness_diff >= self._brightness_manual_threshold_pct
            ):
                self._current_state = STATE_MANUAL
                self._last_manual_reason = (
                    f"brightness changed (motion activation disabled): {entity_id}"
                )
                # Start extended timer immediately for energy saving
                self._start_timer(TIMER_EXTENDED)
                _LOGGER.debug(
                    "Motion activation OFF → brightness changed → MANUAL with timer"
                )
                self._record_event(
                    f"motion_disabled_brightness_manual_with_timer:{entity_id}"
                )
            return

        if self._current_state == STATE_MOTION_AUTO:
            # External change during MOTION-AUTO → MOTION-MANUAL, defer timer until motion=OFF
            if (
                brightness_diff >= self._brightness_manual_threshold_pct
                or new_state.state != old_state.state
            ):
                self._current_state = STATE_MOTION_MANUAL
                self._last_manual_reason = f"external change during motion: {entity_id}"
                _LOGGER.debug(
                    "External change during MOTION-AUTO → MOTION-MANUAL (defer timer)"
                )
                self._record_event(f"motion_auto_to_motion_manual:{entity_id}")
        elif self._current_state == STATE_MOTION_MANUAL:
            # Already motion-manual; keep state (no timer while motion is ON)
            self._record_event(f"motion_manual_change:{entity_id}")
        elif self._current_state == STATE_AUTO:
            # If AUTO and user turned lights OFF → MANUAL-OFF + ExtendedTimer (temporary override to block auto-on)
            if old_state.state == "on" and new_state.state == "off":
                self._cancel_active_timer()
                self._current_state = STATE_MANUAL_OFF
                self._last_manual_reason = f"light turned off during auto: {entity_id}"
                self._start_timer(TIMER_EXTENDED)
                _LOGGER.debug("External off during AUTO → MANUAL-OFF + ExtendedTimer")
                self._record_event(f"auto_to_manual_off:{entity_id}")
            # Else any other significant change → MANUAL + ExtendedTimer
            elif (
                brightness_diff >= self._brightness_manual_threshold_pct
                or new_state.state != old_state.state
            ):
                self._cancel_active_timer()
                self._current_state = STATE_MANUAL
                self._last_manual_reason = f"external change during auto: {entity_id}"
                self._start_timer(TIMER_EXTENDED)
                _LOGGER.debug("External change during AUTO → MANUAL + ExtendedTimer")
                self._record_event(f"auto_to_manual:{entity_id}")
        elif self._current_state == STATE_IDLE:
            # In IDLE, an external ON or brightness change means user took control → MANUAL + ExtendedTimer
            if new_state.state == "on" and old_state.state == "off":
                self._current_state = STATE_MANUAL
                self._last_manual_reason = f"light turned on while idle: {entity_id}"
                self._start_timer(TIMER_EXTENDED)
                _LOGGER.debug("External on during IDLE → MANUAL + ExtendedTimer")
                self._record_event(f"idle_to_manual_on:{entity_id}")
            elif (
                new_state.state == "on"
                and brightness_diff >= self._brightness_manual_threshold_pct
            ):
                self._current_state = STATE_MANUAL
                self._last_manual_reason = f"brightness changed while idle: {entity_id}"
                self._start_timer(TIMER_EXTENDED)
                _LOGGER.debug(
                    "External brightness change during IDLE → MANUAL + ExtendedTimer"
                )
                self._record_event(f"idle_to_manual_brightness:{entity_id}")
        # Note: do not auto-transition here; other states are handled above

    def _any_configured_lights_on(self) -> bool:
        """Check if any configured lights are currently on."""
        for light in self._all_configured_lights():
            state = self.hass.states.get(light)
            if state is not None and state.state == "on":
                return True
        return False

    def _capture_initial_light_states(self) -> None:
        """Capture initial state of all lights."""
        for light in self._all_configured_lights():
            state = self.hass.states.get(light)
            if state:
                brightness_pct = self._get_brightness_percent(state)
                self._tracked_lights[light] = {
                    "state": state.state,
                    "brightness": brightness_pct,
                    "last_changed": dt_util.now(),
                    "integration_origin": False,
                }
                _LOGGER.debug(
                    "Initial state for %s: %s at %d%%",
                    light,
                    state.state,
                    brightness_pct,
                )

    # Done capturing initial states for configured lights

    def _get_brightness_percent(self, state) -> int:
        """Convert brightness to percentage."""
        if state.state != "on":
            return 0

        raw_brightness = state.attributes.get("brightness", 0) or 0
        return int(raw_brightness * 100 / 255) if raw_brightness else 0

    def _is_override_active(self) -> bool:
        """Check if override switch is active."""
        if not self.override_switch:
            return False
        if isinstance(self.override_switch, (list, tuple, set)):
            for ov in self.override_switch:
                st = self.hass.states.get(ov)
                if st is not None and st.state == "on":
                    return True
            return False
        override_state = self.hass.states.get(self.override_switch)
        return override_state is not None and override_state.state == "on"

    def _determine_lights_and_brightness(self) -> tuple[list[str], int]:
        """Determine which lights to turn on and at what brightness."""
        # Night/day is determined by the configured dark-outside switch if provided;
        # otherwise default to day mode.
        dark_outside_state = None
        is_night_mode = False
        if self.dark_outside:
            dark_entity = self.hass.states.get(self.dark_outside)
            dark_outside_state = dark_entity.state if dark_entity else "unavailable"
            is_night_mode = bool(dark_entity and dark_entity.state == "on")

        if is_night_mode:
            # Night: only background lights, night brightness
            lights_to_turn_on = (
                list(self.background_lights) if self.brightness_night > 0 else []
            )
            target_brightness = self.brightness_night
        else:
            # Day: all configured lights, day brightness
            lights_to_turn_on = [
                light
                for light in self._all_configured_lights()
                if self.brightness_day > 0
            ]
            target_brightness = self.brightness_day

        _LOGGER.debug(
            "Motion detection: %s mode, %d%% brightness, %d lights selected (dark_outside=%s)",
            "night" if is_night_mode else "day",
            target_brightness,
            len(lights_to_turn_on),
            dark_outside_state or "not-configured",
        )

        if not lights_to_turn_on and not is_night_mode:
            _LOGGER.info(
                "Day mode with 0%% brightness - no automatic lights will be activated on motion"
            )

        return lights_to_turn_on, target_brightness

    async def _async_set_light_state(
        self, light: str, state: str, brightness: int
    ) -> None:
        """Set the state of a single light."""
        try:
            service_data = {"entity_id": light}
            if state == "on" and brightness > 0:
                service_data["brightness_pct"] = brightness

            # Create a context so we can later detect that the state change came from this integration
            ctx = Context()
            await self.hass.services.async_call(
                "light", f"turn_{state}", service_data, context=ctx
            )
            self._register_integration_context(ctx)
            _LOGGER.debug("Set %s to %s at %d%%", light, state, brightness)
        except (OSError, TimeoutError) as err:
            _LOGGER.error("Error setting state for light %s: %s", light, err)

    def _update_light_data(self) -> None:
        """Update coordinator data with current light states."""
        lights_on = sum(
            1 for light in self._tracked_lights.values() if light["state"] == "on"
        )
        total_lights = len(self._tracked_lights)

        self.data = {
            "lights_tracked": total_lights,
            "lights_on": lights_on,
            "lights_off": total_lights - lights_on,
            "light_states": dict(self._tracked_lights),
            "current_state": self._current_state,
            "timer_active": self._active_timer is not None,
            "timer_type": self._timer_type,
            "timer_end_time": self._timer_end_time.isoformat()
            if self._timer_end_time
            else None,
        }

        _LOGGER.debug(
            "Light tracking updated: %d/%d lights on, state=%s, tracked_lights=%d",
            lights_on,
            total_lights,
            self._current_state,
            len(self._tracked_lights),
        )
        if total_lights == 0:
            _LOGGER.warning(
                "No lights are being tracked! Configured lights: %s. This may indicate entity availability issues",
                self._all_configured_lights(),
            )
        self.async_update_listeners()

    async def async_refresh_light_tracking(self) -> None:
        """Refresh light tracking if entities became available."""
        if any(
            light not in self._tracked_lights for light in self._all_configured_lights()
        ):
            _LOGGER.info("Refreshing light tracking due to missing entity")
            self._capture_initial_light_states()
            self._update_light_data()

    def async_cleanup_listeners(self) -> None:
        """Clean up event listeners."""
        count = len(self._unsubscribers)
        for unsubscriber in self._unsubscribers:
            unsubscriber()
        self._unsubscribers.clear()
        # Cancel any active timer
        self._cancel_active_timer()
        _LOGGER.debug(
            "Cleaned up %d light tracking listeners and cancelled active timer", count
        )

    # Properties for sensor access
    @property
    def current_state(self) -> str:
        """Get current state."""
        return self._current_state

    @property
    def manual_reason(self) -> str | None:
        """Return reason for manual state."""
        return self._last_manual_reason

    @property
    def event_log(self) -> list[dict[str, str]]:
        """Return recent chronological event log (newest last)."""
        return [{"time": ts.isoformat(), "event": ev} for ts, ev in self._event_log]

    def _record_event(self, event: str) -> None:
        """Record an event with timestamp for diagnostics."""
        self._event_log.append((dt_util.now(), event))

    @property
    def motion_entity_id(self) -> str:
        """Get motion entity ID."""
        return self.motion_entity

    @property
    def no_motion_wait_seconds(self) -> int:
        """Get no motion wait time in seconds."""
        return self._no_motion_wait

    @property
    def day_brightness(self) -> int:
        """Get day brightness setting."""
        return self.brightness_day

    @property
    def night_brightness(self) -> int:
        """Get night brightness setting."""
        return self.brightness_night

    @property
    def background_light_entity(self) -> str:
        """Return a representative background light entity (first configured)."""
        return self.background_light

    @property
    def feature_light_entity(self) -> str:
        """Return a representative feature light entity (first configured)."""
        return self.feature_light

    @property
    def ceiling_light_entity(self) -> str:
        """Return a representative ceiling light entity (first configured)."""
        return self.ceiling_light

    @property
    def is_motion_activation_enabled(self) -> bool:
        """Get motion activation setting."""
        return self.motion_activation

    @property
    def current_motion_state(self) -> str:
        """Get current motion sensor state."""
        if not self.motion_entities:
            return "unknown"
        any_on = False
        any_known = False
        for ent in self.motion_entities:
            st = self.hass.states.get(ent)
            if st is None:
                continue
            any_known = True
            if st.state == "on":
                any_on = True
                break
        if not any_known:
            return "unknown"
        return "on" if any_on else "off"

    @property
    def is_override_active(self) -> bool:
        """Check if override is active."""
        return self._is_override_active()

    @property
    def last_action_time(self):  # type: ignore[override]
        """Get last action time (fallback to last motion time)."""
        return self._last_motion_time or dt_util.now()

    @property
    def last_action(self) -> str:  # type: ignore[override]
        """Get last action description."""
        if self._last_motion_time:
            return "Motion detected"
        return "Motion coordinator active"

    @property
    def last_motion_time(self):
        """Get last motion time."""
        return self._last_motion_time

    @property
    def time_until_action(self) -> int | None:
        """Get seconds until next action."""
        if self._timer_end_time:
            remaining = (self._timer_end_time - dt_util.now()).total_seconds()
            return max(0, int(remaining))
        return None

    def _register_integration_context(self, ctx: Context) -> None:
        """Register a context id for later origin detection."""
        now = time.monotonic()
        self._recent_context_ids.add(ctx.id)
        self._context_queue.append((ctx.id, now))
        self._purge_old_context_ids(now)

    def _purge_old_context_ids(self, now: float | None = None) -> None:
        """Purge expired context ids beyond retention window."""
        if now is None:
            now = time.monotonic()
        cutoff = now - self._max_context_age_seconds
        while self._context_queue and self._context_queue[0][1] < cutoff:
            expired_id, _ = self._context_queue.popleft()
            self._recent_context_ids.discard(expired_id)

    @property
    def diagnostic_info(self) -> dict[str, Any]:
        """Get diagnostic information for troubleshooting."""
        configured = {
            "background_lights": list(self.background_lights),
            "feature_lights": list(self.feature_lights),
            "ceiling_lights": list(self.ceiling_lights),
        }
        flattened = self._all_configured_lights()
        return {
            "configured_lights": configured,
            "dark_outside": self.dark_outside or None,
            "tracked_lights_count": len(self._tracked_lights),
            "tracked_light_ids": list(self._tracked_lights.keys()),
            "missing_lights": [
                light_id
                for light_id in flattened
                if light_id not in self._tracked_lights
            ],
            "available_entities": {
                "motion_sensors": {
                    ent: self.hass.states.get(ent) is not None
                    for ent in self.motion_entities
                },
                "override_switch": (
                    {
                        ov: self.hass.states.get(ov) is not None
                        for ov in (self.override_switch or [])
                    }
                    if isinstance(self.override_switch, (list, tuple, set))
                    else (
                        self.hass.states.get(self.override_switch) is not None
                        if self.override_switch
                        else False
                    )
                ),
                "lights": {
                    lid: self.hass.states.get(lid) is not None for lid in flattened
                },
            },
            "listeners_count": len(self._unsubscribers),
            "current_state": self._current_state,
        }

    def _all_configured_lights(self) -> list[str]:
        """Return a de-duplicated flat list of all configured lights."""
        combined: list[str] = []
        combined.extend(self.background_lights)
        combined.extend(self.feature_lights)
        combined.extend(self.ceiling_lights)
        # De-duplicate while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for light in combined:
            if light and light not in seen:
                seen.add(light)
                result.append(light)
        return result

    def _is_integration_context(self, ctx: Context | None) -> bool:
        """Return True if the context belongs to an integration-originated service call."""
        if ctx is None:
            return False
        self._purge_old_context_ids()
        if ctx.id in self._recent_context_ids:
            return True
        if ctx.parent_id and ctx.parent_id in self._recent_context_ids:
            return True
        return False
