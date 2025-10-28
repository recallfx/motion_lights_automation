"""Motion Lights Coordinator using modular architecture."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_EXTENDED_TIMEOUT,
    CONF_HOUSE_ACTIVE,
    CONF_LIGHTS,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_DELAY,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
    DEFAULT_AMBIENT_LIGHT_THRESHOLD,
    DEFAULT_BRIGHTNESS_ACTIVE,
    DEFAULT_BRIGHTNESS_INACTIVE,
    DEFAULT_EXTENDED_TIMEOUT,
    DEFAULT_MOTION_ACTIVATION,
    DEFAULT_MOTION_DELAY,
    DEFAULT_NO_MOTION_WAIT,
    DOMAIN,
    STATE_AUTO,
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_MOTION_AUTO,
    STATE_MOTION_MANUAL,
    STATE_OVERRIDDEN,
)
from .light_controller import (
    LightController,
    TimeOfDayBrightnessStrategy,
)
from .manual_detection import BrightnessThresholdStrategy, ManualInterventionDetector
from .state_machine import MotionLightsStateMachine, StateTransitionEvent
from .timer_manager import TimerManager, TimerType
from .triggers import MotionTrigger, OverrideTrigger, TriggerManager

_LOGGER = logging.getLogger(__name__)


class MotionLightsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Motion Lights coordinator using modular architecture.

    This coordinator delegates to specialized modules for clean separation of concerns.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the refactored coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_motion_v2",
            update_interval=None,
            config_entry=config_entry,
        )

        self.config_entry = config_entry
        self._load_config()

        # Initialize modular components
        self.state_machine = MotionLightsStateMachine(initial_state=STATE_IDLE)
        self.timer_manager = TimerManager(hass)
        self.trigger_manager = TriggerManager(hass)

        # Light controller with brightness strategy
        lights = self._lights
        self.light_controller = LightController(
            hass,
            lights,
            brightness_strategy=TimeOfDayBrightnessStrategy(
                active_brightness=self.brightness_active,
                inactive_brightness=self.brightness_inactive,
            ),
        )

        # Manual intervention detector
        self.manual_detector = ManualInterventionDetector()
        brightness_strategy = BrightnessThresholdStrategy()
        # ManualInterventionDetector uses set_strategy to configure the strategy
        self.manual_detector.set_strategy(brightness_strategy)

        # Set timer durations
        self.timer_manager.set_default_duration(TimerType.MOTION, self._no_motion_wait)
        self.timer_manager.set_default_duration(
            TimerType.EXTENDED, self.extended_timeout
        )

        # Tracking
        self._unsubscribers: list = []
        self._cleanup_handle = None
        self.data = {}

        # Event tracking for diagnostics
        self._events: list[dict[str, Any]] = []
        self._max_events = 100
        self._last_transition_reason: str | None = None
        self._last_transition_time: datetime | None = None

    def _load_config(self) -> None:
        """Load configuration."""
        data = self.config_entry.data

        def _as_list(value: Any) -> list[str]:
            if value is None:
                return []
            if isinstance(value, str):
                return [value]
            if isinstance(value, (list, tuple, set)):
                return [str(v) for v in value]
            return []

        # Motion activation
        self.motion_activation = data.get(
            CONF_MOTION_ACTIVATION, DEFAULT_MOTION_ACTIVATION
        )
        self._motion_delay = data.get(CONF_MOTION_DELAY, DEFAULT_MOTION_DELAY)
        self._no_motion_wait = data.get(CONF_NO_MOTION_WAIT, DEFAULT_NO_MOTION_WAIT)
        self.extended_timeout = data.get(
            CONF_EXTENDED_TIMEOUT, DEFAULT_EXTENDED_TIMEOUT
        )

        # Entities
        self.motion_entities = _as_list(data.get(CONF_MOTION_ENTITY))
        override_cfg = data.get(CONF_OVERRIDE_SWITCH)
        if isinstance(override_cfg, (list, tuple, set)):
            override_list = [str(v) for v in override_cfg if v]
            self.override_switch = override_list[0] if override_list else None
        else:
            self.override_switch = str(override_cfg) if override_cfg else None

        # Ambient light sensor and house active - handle both string and list
        ambient_cfg = data.get(CONF_AMBIENT_LIGHT_SENSOR)
        if isinstance(ambient_cfg, (list, tuple, set)):
            ambient_list = [str(v) for v in ambient_cfg if v]
            self.ambient_light_sensor = ambient_list[0] if ambient_list else None
        else:
            self.ambient_light_sensor = str(ambient_cfg) if ambient_cfg else None

        self.ambient_light_threshold = data.get(
            CONF_AMBIENT_LIGHT_THRESHOLD, DEFAULT_AMBIENT_LIGHT_THRESHOLD
        )

        house_cfg = data.get(CONF_HOUSE_ACTIVE)
        if isinstance(house_cfg, (list, tuple, set)):
            house_list = [str(v) for v in house_cfg if v]
            self.house_active = house_list[0] if house_list else None
        else:
            self.house_active = str(house_cfg) if house_cfg else None

        self.brightness_active = data.get(
            CONF_BRIGHTNESS_ACTIVE, DEFAULT_BRIGHTNESS_ACTIVE
        )
        self.brightness_inactive = data.get(
            CONF_BRIGHTNESS_INACTIVE, DEFAULT_BRIGHTNESS_INACTIVE
        )

        # Brightness mode state for hysteresis (starts as None, determined on first check)
        self._brightness_mode_is_dim: bool | None = None

        # Lights
        self._lights = _as_list(data.get(CONF_LIGHTS))

    async def async_setup_listeners(self) -> None:
        """Set up the coordinator - wire modules together."""
        import time

        start_time = time.monotonic()

        # Set up state machine callbacks
        self.state_machine.on_enter_state(STATE_MOTION_AUTO, self._on_enter_motion_auto)
        self.state_machine.on_enter_state(STATE_AUTO, self._on_enter_auto)
        self.state_machine.on_enter_state(STATE_MANUAL, self._on_enter_manual)
        self.state_machine.on_enter_state(STATE_MANUAL_OFF, self._on_enter_manual_off)
        self.state_machine.on_enter_state(STATE_IDLE, self._on_enter_idle)
        self.state_machine.on_transition(self._on_transition)

        # Set up motion trigger
        if self.motion_entities:
            motion_trigger = MotionTrigger(
                self.hass,
                {
                    "entity_ids": self.motion_entities,
                    "enabled": self.motion_activation,
                },
            )
            motion_trigger.on_activated(self._handle_motion_on)
            motion_trigger.on_deactivated(self._handle_motion_off)
            self.trigger_manager.add_trigger("motion", motion_trigger)

        # Set up override trigger
        if self.override_switch:
            override_trigger = OverrideTrigger(
                self.hass, {"entity_id": self.override_switch}
            )
            override_trigger.on_activated(self._handle_override_on)
            override_trigger.on_deactivated(self._handle_override_off)
            self.trigger_manager.add_trigger("override", override_trigger)

        # Set up all triggers
        await self.trigger_manager.async_setup_all()

        # Set up light monitoring
        all_lights = self.light_controller.get_all_lights()
        if all_lights:
            self._unsubscribers.append(
                async_track_state_change_event(
                    self.hass,
                    all_lights,
                    self._async_light_changed,
                )
            )

        # Set up ambient light sensor monitoring
        if self.ambient_light_sensor:
            self._unsubscribers.append(
                async_track_state_change_event(
                    self.hass,
                    [self.ambient_light_sensor],
                    self._async_ambient_light_changed,
                )
            )

        # Set up house active monitoring
        if self.house_active:
            self._unsubscribers.append(
                async_track_state_change_event(
                    self.hass,
                    [self.house_active],
                    self._async_house_active_changed,
                )
            )

        # Initialize light states
        self.light_controller.refresh_all_states()

        # Set initial state
        self._set_initial_state()

        # Update data
        self._update_data()

        # Schedule periodic cleanup of old context IDs (every hour)
        self._schedule_periodic_cleanup()

        # Log startup performance
        elapsed = time.monotonic() - start_time
        total_lights = len(all_lights) if all_lights else 0
        active_timers = (
            self.timer_manager._timers.__len__()
            if hasattr(self.timer_manager, "_timers")
            else 0
        )

        _LOGGER.info(
            "Motion Lights Automation initialized: %.2fs | Lights: %d | Timers: %d | "
            "Motion activation: %s | Override: %s | Ambient light sensor: %s",
            elapsed,
            total_lights,
            active_timers,
            self.motion_activation,
            bool(self.override_switch),
            bool(self.ambient_light_sensor),
        )

    def _set_initial_state(self) -> None:
        """Set initial state based on current conditions."""
        override_trigger = self.trigger_manager.get_trigger("override")
        if override_trigger and override_trigger.is_active():
            self.state_machine.force_state(STATE_OVERRIDDEN)
        elif self.light_controller.any_lights_on():
            self.state_machine.force_state(STATE_MANUAL)
            if not self.motion_activation:
                self.timer_manager.start_timer(
                    "extended",
                    TimerType.EXTENDED,
                    self._async_timer_expired,
                )
        else:
            self.state_machine.force_state(STATE_IDLE)

    # ========================================================================
    # Trigger Event Handlers
    # ========================================================================

    def _handle_motion_on(self) -> None:
        """Handle motion detected."""
        try:
            _LOGGER.info("Motion ON")
            self._log_event("motion_on", {"motion_activation": self.motion_activation})

            if not self.motion_activation:
                # When motion_activation is disabled, motion doesn't turn on lights automatically.
                # However, if lights are already on (manually), restart the timer to prevent
                # premature shutoff while the room is actively being used.
                current = self.state_machine.current_state
                if current in (STATE_MANUAL, STATE_AUTO):
                    _LOGGER.debug(
                        "Motion detected with motion_activation=False in state %s; restarting extended timer",
                        current,
                    )
                    self.timer_manager.cancel_timer("extended")
                    self.timer_manager.start_timer(
                        "extended",
                        TimerType.EXTENDED,
                        self._async_timer_expired,
                    )
                elif current == STATE_MANUAL_OFF:
                    # User manually turned off lights but motion detected - restart timer
                    _LOGGER.debug(
                        "Motion detected with motion_activation=False in MANUAL_OFF state; restarting extended timer"
                    )
                    self.timer_manager.cancel_timer("extended")
                    self.timer_manager.start_timer(
                        "extended",
                        TimerType.EXTENDED,
                        self._async_timer_expired,
                    )
                return

            current = self.state_machine.current_state

            if current == STATE_MANUAL:
                self.state_machine.transition(StateTransitionEvent.MOTION_ON)
            elif current == STATE_AUTO:
                self.timer_manager.cancel_all_timers()
                self.state_machine.transition(StateTransitionEvent.MOTION_ON)
            elif current in (STATE_IDLE, STATE_MANUAL_OFF):
                # Check if motion delay is configured
                if self._motion_delay > 0:
                    _LOGGER.debug(
                        "Motion detected in %s state, starting %ds delay timer",
                        current,
                        self._motion_delay,
                    )
                    # Start delay timer - will trigger activation if motion still active
                    self.timer_manager.start_timer(
                        "motion_delay",
                        TimerType.CUSTOM,
                        self._async_motion_delay_expired,
                        duration=self._motion_delay,
                    )
                else:
                    # No delay - immediate activation
                    self.state_machine.transition(StateTransitionEvent.MOTION_ON)
        except Exception:
            _LOGGER.exception("Error in motion ON handler")

    def _handle_motion_off(self) -> None:
        """Handle motion cleared."""
        try:
            _LOGGER.info("Motion OFF")
            self._log_event(
                "motion_off", {"current_state": self.state_machine.current_state}
            )

            current = self.state_machine.current_state

            if current == STATE_MOTION_AUTO:
                self.state_machine.transition(StateTransitionEvent.MOTION_OFF)
            elif current == STATE_MOTION_MANUAL:
                self.state_machine.transition(StateTransitionEvent.MOTION_OFF)
        except Exception:
            _LOGGER.exception("Error in motion OFF handler")

    def _handle_override_on(self) -> None:
        """Handle override activated."""
        try:
            _LOGGER.info(
                "Override ON - current state: %s", self.state_machine.current_state
            )
            self._log_event(
                "override_on", {"current_state": self.state_machine.current_state}
            )
            self.timer_manager.cancel_all_timers()
            result = self.state_machine.transition(StateTransitionEvent.OVERRIDE_ON)
            _LOGGER.info(
                "Override ON transition result: %s, new state: %s",
                result,
                self.state_machine.current_state,
            )
            self._update_data()
        except Exception:
            _LOGGER.exception("Error in override ON handler")

    def _handle_override_off(self) -> None:
        """Handle override deactivated."""
        try:
            _LOGGER.info(
                "Override OFF - current state: %s", self.state_machine.current_state
            )
            self._log_event(
                "override_off", {"current_state": self.state_machine.current_state}
            )
            if self.light_controller.any_lights_on():
                result = self.state_machine.transition(
                    StateTransitionEvent.OVERRIDE_OFF,
                    target_state=STATE_MANUAL,
                )
                _LOGGER.info("Override OFF transition to MANUAL result: %s", result)
            else:
                result = self.state_machine.transition(
                    StateTransitionEvent.OVERRIDE_OFF,
                    target_state=STATE_IDLE,
                )
                _LOGGER.info("Override OFF transition to IDLE result: %s", result)
            _LOGGER.info("Override OFF new state: %s", self.state_machine.current_state)
            self._update_data()
        except Exception:
            _LOGGER.exception("Error in override OFF handler")

    @callback
    def _async_light_changed(self, event: Event) -> None:
        """Handle light state change."""
        try:
            entity_id = event.data.get("entity_id")
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")

            if not new_state or not old_state:
                return

            # Update light controller state
            self.light_controller.update_light_state(entity_id, new_state)

            # Check for manual intervention
            manual_intervention_handled = False
            if not self.light_controller.is_integration_context(new_state.context):
                is_manual = self.manual_detector.check_intervention(
                    entity_id, old_state, new_state, new_state.context
                )

                if is_manual:
                    old_state_before_intervention = self.state_machine.current_state
                    self._handle_manual_intervention(entity_id, old_state, new_state)
                    # If we transitioned to MANUAL_OFF, don't process LIGHTS_ALL_OFF
                    if (
                        old_state_before_intervention
                        in (STATE_AUTO, STATE_MANUAL, STATE_MOTION_MANUAL)
                        and self.state_machine.current_state == STATE_MANUAL_OFF
                    ):
                        manual_intervention_handled = True

            # Check if all lights are off (but skip if we just handled manual intervention to MANUAL_OFF)
            if (
                not manual_intervention_handled
                and not self.light_controller.any_lights_on()
            ):
                if self.state_machine.current_state not in (
                    STATE_OVERRIDDEN,
                    STATE_MANUAL_OFF,
                ):
                    self.timer_manager.cancel_all_timers()
                    self.state_machine.transition(StateTransitionEvent.LIGHTS_ALL_OFF)

            self._update_data()
        except Exception:
            _LOGGER.exception("Error in light changed handler")

    def _handle_manual_intervention(self, entity_id, old_state, new_state) -> None:
        """Handle manual intervention detected."""
        current = self.state_machine.current_state

        change_type = "ON" if new_state.state == "on" else "OFF"
        brightness = new_state.attributes.get("brightness", "N/A")

        _LOGGER.debug(
            "Manual intervention detected: %s changed to %s (brightness=%s) in %s state",
            entity_id,
            change_type,
            brightness,
            current,
        )

        if current == STATE_MOTION_AUTO:
            self.state_machine.transition(StateTransitionEvent.MANUAL_INTERVENTION)
        elif current == STATE_MOTION_MANUAL:
            # Check if user turned off all lights during motion manual state
            if new_state.state == "off" and old_state.state == "on":
                if not self.light_controller.any_lights_on():
                    # All lights turned off, transition to MANUAL_OFF
                    _LOGGER.info(
                        "User turned off all lights in MOTION_MANUAL state - transitioning to MANUAL_OFF"
                    )
                    self.state_machine.transition(
                        StateTransitionEvent.MANUAL_OFF_INTERVENTION
                    )
                    return  # Don't continue processing
            # Already in manual mode during motion, log but don't restart timers
            _LOGGER.debug(
                "Manual change during MOTION_MANUAL state - already tracking manually, no timer to restart"
            )
        elif current == STATE_MANUAL:
            # User is actively adjusting lights in MANUAL state
            if new_state.state == "off" and old_state.state == "on":
                # User turned off a light - check if all lights are off
                if not self.light_controller.any_lights_on():
                    # All lights turned off, transition to MANUAL_OFF
                    _LOGGER.info(
                        "User turned off all lights in MANUAL state - transitioning to MANUAL_OFF"
                    )
                    self.state_machine.transition(
                        StateTransitionEvent.MANUAL_OFF_INTERVENTION
                    )
                else:
                    # Some lights still on, restart timer
                    _LOGGER.info(
                        "User turned off a light in MANUAL state - restarting extended timer"
                    )
                    self.timer_manager.cancel_timer("extended")
                    self.timer_manager.start_timer(
                        "extended",
                        TimerType.EXTENDED,
                        self._async_timer_expired,
                    )
            else:
                # Brightness adjustment or turning on more lights - restart the extended timer
                _LOGGER.info(
                    "Manual adjustment in MANUAL state - restarting extended timer"
                )
                self.timer_manager.cancel_timer("extended")
                self.timer_manager.start_timer(
                    "extended",
                    TimerType.EXTENDED,
                    self._async_timer_expired,
                )
        elif current == STATE_AUTO:
            if new_state.state == "off" and old_state.state == "on":
                # User turned off a light - check if ALL lights are now off
                if not self.light_controller.any_lights_on():
                    # All lights turned off, transition to MANUAL_OFF
                    _LOGGER.info(
                        "User turned off all lights in AUTO state - transitioning to MANUAL_OFF"
                    )
                    self.state_machine.transition(
                        StateTransitionEvent.MANUAL_OFF_INTERVENTION
                    )
                else:
                    # Some lights still on, transition to MANUAL
                    _LOGGER.info(
                        "User turned off a light in AUTO state but some remain on - transitioning to MANUAL"
                    )
                    self.state_machine.transition(
                        StateTransitionEvent.MANUAL_INTERVENTION
                    )
            else:
                self.state_machine.transition(StateTransitionEvent.MANUAL_INTERVENTION)
        elif current == STATE_MANUAL_OFF:
            # User manually turned off lights, but now they're adjusting them again
            # This means they're still active, so transition to MANUAL state
            if new_state.state == "on" or (
                new_state.state == "on" and old_state.state == "on"
            ):
                _LOGGER.info(
                    "Manual adjustment in MANUAL_OFF state - user is active, transitioning to MANUAL"
                )
                self.state_machine.transition(StateTransitionEvent.MANUAL_INTERVENTION)
            else:
                # Another light turned off - just restart the extended timer
                _LOGGER.info(
                    "Additional manual OFF in MANUAL_OFF state - restarting extended timer"
                )
                self.timer_manager.cancel_timer("extended")
                self.timer_manager.start_timer(
                    "extended",
                    TimerType.EXTENDED,
                    self._async_timer_expired,
                )
        elif current == STATE_IDLE:
            if new_state.state == "on":
                self.state_machine.transition(StateTransitionEvent.MANUAL_INTERVENTION)

    async def _async_ambient_light_changed(self, event: Event) -> None:
        """Handle ambient light sensor state change.

        When ambient light changes, re-evaluate whether lights should be on or off:
        - If it becomes dark and motion is active: turn on lights
        - If it becomes bright: turn off auto-controlled lights
        """
        try:
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")

            if not new_state or not old_state:
                return

            # Get context to evaluate current ambient conditions
            context = self._get_context()
            is_dark_now = context.get("is_dark_inside", True)

            # Determine if darkness state changed (with hysteresis for lux sensors)
            old_is_dark = self._evaluate_darkness_from_state(old_state)

            if old_is_dark == is_dark_now:
                # No effective change in darkness state
                _LOGGER.debug(
                    "Ambient light sensor changed but darkness state unchanged (is_dark=%s)",
                    is_dark_now,
                )
                return

            _LOGGER.info(
                "Ambient light condition changed: %s -> %s (is_dark=%s)",
                old_state.state,
                new_state.state,
                is_dark_now,
            )
            self._log_event(
                "ambient_light_changed",
                {
                    "old_state": old_state.state,
                    "new_state": new_state.state,
                    "is_dark": is_dark_now,
                },
            )

            current = self.state_machine.current_state
            motion_trigger = self.trigger_manager.get_trigger("motion")
            motion_active = motion_trigger.is_active() if motion_trigger else False

            # If it became dark and we have motion and motion_activation is enabled
            if is_dark_now and motion_active and self.motion_activation:
                if current in (STATE_IDLE, STATE_MANUAL_OFF):
                    _LOGGER.info(
                        "Became dark with motion active in %s - activating lights",
                        current,
                    )
                    self.state_machine.transition(StateTransitionEvent.MOTION_ON)
                elif current in (STATE_MANUAL, STATE_AUTO, STATE_MOTION_MANUAL):
                    # Lights already on - adjust brightness if needed
                    _LOGGER.debug(
                        "Became dark in %s - re-evaluating brightness",
                        current,
                    )
                    await self._async_turn_on_lights()

            # If it became bright, turn off auto-controlled lights
            elif not is_dark_now:
                if current in (STATE_AUTO, STATE_MOTION_AUTO):
                    _LOGGER.info(
                        "Became bright in %s - turning off auto-controlled lights",
                        current,
                    )
                    self.timer_manager.cancel_all_timers()
                    await self._async_turn_off_lights()
                    # Transition to appropriate state based on whether lights stay on
                    # The light change handler will transition to IDLE if all lights are off
                elif current in (STATE_MOTION_MANUAL, STATE_MANUAL):
                    # Lights are manually controlled - just adjust brightness to 0 (off)
                    # But don't force them off if user wants them on
                    _LOGGER.debug(
                        "Became bright in %s - lights are manually controlled, not forcing off",
                        current,
                    )

            self._update_data()
        except Exception:
            _LOGGER.exception("Error in ambient light changed handler")

    async def _async_house_active_changed(self, event: Event) -> None:
        """Handle house active state change.

        When house active state changes, adjust brightness of currently lit lights:
        - If house becomes active: increase brightness
        - If house becomes inactive: decrease brightness
        """
        try:
            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")

            if not new_state or not old_state:
                return

            old_is_active = old_state.state == "on"
            new_is_active = new_state.state == "on"

            if old_is_active == new_is_active:
                # No change
                return

            _LOGGER.info(
                "House active state changed: %s -> %s",
                old_state.state,
                new_state.state,
            )
            self._log_event(
                "house_active_changed",
                {
                    "old_state": old_state.state,
                    "new_state": new_state.state,
                    "is_active": new_is_active,
                },
            )

            current = self.state_machine.current_state

            # Only adjust brightness if lights are currently on in auto-controlled states
            if current in (
                STATE_AUTO,
                STATE_MOTION_AUTO,
                STATE_MOTION_MANUAL,
                STATE_MANUAL,
            ):
                if self.light_controller.any_lights_on():
                    _LOGGER.debug(
                        "House active changed in %s with lights on - adjusting brightness",
                        current,
                    )
                    # Re-apply lights with new brightness based on updated house_active state
                    await self._async_turn_on_lights()

            self._update_data()
        except Exception:
            _LOGGER.exception("Error in house active changed handler")

    def _evaluate_darkness_from_state(self, state) -> bool:
        """Evaluate if it's dark based on a given state object.

        This is used to detect actual changes in darkness vs just sensor value fluctuations.
        """
        if not self.ambient_light_sensor or not state:
            return True

        unit = state.attributes.get("unit_of_measurement")

        if unit == "lx":
            try:
                lux = float(state.state)
                return self._evaluate_lux_with_hysteresis(lux)
            except (ValueError, TypeError):
                return True
        else:
            # Binary representation
            return state.state in ("on", "true", "True", "1")

    # ========================================================================
    # State Entry Callbacks
    # ========================================================================

    def _on_enter_motion_auto(self, state=None, from_state=None, event=None) -> None:
        """Entering MOTION_AUTO - turn on lights."""
        _LOGGER.debug("Entering MOTION_AUTO state (from %s)", from_state)
        self.hass.async_create_task(self._async_turn_on_lights())

    def _on_enter_auto(self, state=None, from_state=None, event=None) -> None:
        """Entering AUTO - start motion timer."""
        _LOGGER.debug("Entering AUTO state - starting motion timer")
        self.timer_manager.start_timer(
            "motion",
            TimerType.MOTION,
            self._async_timer_expired,
        )

    def _on_enter_manual(self, state=None, from_state=None, event=None) -> None:
        """Entering MANUAL - start extended timer."""
        _LOGGER.debug("Entering MANUAL state - starting extended timer")
        self.timer_manager.cancel_timer("motion")
        self.timer_manager.start_timer(
            "extended",
            TimerType.EXTENDED,
            self._async_timer_expired,
        )

    def _on_enter_manual_off(self, state=None, from_state=None, event=None) -> None:
        """Entering MANUAL_OFF - start extended timer."""
        _LOGGER.debug(
            "Entering MANUAL_OFF state - cancelling motion timer, starting extended timer"
        )
        self.timer_manager.cancel_timer("motion")  # Cancel any existing motion timer
        self.timer_manager.start_timer(
            "extended",
            TimerType.EXTENDED,
            self._async_timer_expired,
        )

    def _on_enter_idle(self, state=None, from_state=None, event=None) -> None:
        """Entering IDLE - turn off lights."""
        _LOGGER.debug("Entering IDLE state (from %s) - turning off lights", from_state)
        self.hass.async_create_task(self._async_turn_off_lights())

    def _on_transition(self, old_state: str, new_state: str, event) -> None:
        """Called on any state transition."""
        _LOGGER.info(
            "State transition: %s -> %s (event: %s)", old_state, new_state, event.value
        )
        self._log_transition(old_state, new_state, event.value)
        self._update_data()

    # ========================================================================
    # Timer Callbacks
    # ========================================================================

    async def _async_timer_expired(self, timer_id: str = None) -> None:
        """Timer expired - transition to idle."""
        _LOGGER.info("Timer expired: %s", timer_id)
        self.state_machine.transition(StateTransitionEvent.TIMER_EXPIRED)

    async def _async_motion_delay_expired(self, timer_id: str = None) -> None:
        """Motion delay timer expired - check if motion still active and activate lights."""
        _LOGGER.debug("Motion delay timer expired")

        # Check if motion is still active
        motion_trigger = self.trigger_manager.get_trigger("motion")
        if motion_trigger and motion_trigger.is_active():
            _LOGGER.info(
                "Motion still active after %ds delay - activating lights",
                self._motion_delay,
            )
            self.state_machine.transition(StateTransitionEvent.MOTION_ON)
        else:
            _LOGGER.info(
                "Motion cleared during %ds delay - not activating lights",
                self._motion_delay,
            )

    # ========================================================================
    # Light Control
    # ========================================================================

    async def _async_turn_on_lights(self) -> None:
        """Turn on lights."""
        context = self._get_context()
        await self.light_controller.turn_on_auto_lights(context)
        self._update_data()

    async def _async_turn_off_lights(self) -> None:
        """Turn off lights."""
        await self.light_controller.turn_off_lights()
        self._update_data()

    def _get_context(self):
        """Get context for strategies."""
        is_house_active = True
        is_dark_inside = True

        # Get switch states
        if self.house_active:
            house_state = self.hass.states.get(self.house_active)
            if house_state is None:
                _LOGGER.warning(
                    "house_active entity '%s' not found; assuming house is active",
                    self.house_active,
                )
            else:
                is_house_active = house_state.state == "on"

        # Ambient light sensor with hysteresis support
        if self.ambient_light_sensor:
            sensor_state = self.hass.states.get(self.ambient_light_sensor)
            if sensor_state is None:
                _LOGGER.warning(
                    "ambient_light_sensor entity '%s' not found; assuming low ambient light",
                    self.ambient_light_sensor,
                )
                is_dark_inside = True
            else:
                # Check if it's a lux sensor (numeric) or binary representation
                unit = sensor_state.attributes.get("unit_of_measurement")

                if unit == "lx":
                    # Lux sensor - use hysteresis
                    try:
                        current_lux = float(sensor_state.state)
                        is_dark_inside = self._evaluate_lux_with_hysteresis(current_lux)
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            "Could not parse lux value '%s' from %s; assuming low ambient light",
                            sensor_state.state,
                            self.ambient_light_sensor,
                        )
                        is_dark_inside = True
                else:
                    # Any other sensor - treat as binary representation
                    # ON state means low ambient light (dark inside)
                    # For binary_sensor, switch, input_boolean, etc.
                    is_dark_inside = sensor_state.state in ("on", "true", "True", "1")

        motion_trigger = self.trigger_manager.get_trigger("motion")
        motion_active = motion_trigger.is_active() if motion_trigger else False

        # Return dict-like context that strategies can use
        return {
            "is_dark_inside": is_dark_inside,
            "is_house_active": is_house_active,
            "motion_active": motion_active,
            "current_state": self.state_machine.current_state,
            "all_lights": self.light_controller.get_all_lights(),
        }

    def _evaluate_lux_with_hysteresis(self, current_lux: float) -> bool:
        """Evaluate lux level with hysteresis to prevent flickering.

        Uses ±20 lux gap around the threshold.
        - Threshold 50 lux → LOW range 0-30, HIGH range 70+
        - When in DIM mode: stays dim until lux > threshold + 20
        - When in BRIGHT mode: stays bright until lux < threshold - 20

        Returns:
            bool: True if should use dim brightness (low ambient light)
        """
        threshold = self.ambient_light_threshold
        low_threshold = threshold - 20
        high_threshold = threshold + 20

        # First time evaluation - no previous state
        if self._brightness_mode_is_dim is None:
            # Initialize based on current lux relative to center threshold
            self._brightness_mode_is_dim = current_lux < threshold
            _LOGGER.debug(
                "Initializing brightness mode: lux=%.1f, threshold=%d, mode=%s",
                current_lux,
                threshold,
                "DIM" if self._brightness_mode_is_dim else "BRIGHT",
            )
            return self._brightness_mode_is_dim

        # Currently in DIM mode
        if self._brightness_mode_is_dim:
            # Stay dim unless lux rises above HIGH threshold
            if current_lux >= high_threshold:
                self._brightness_mode_is_dim = False
                _LOGGER.debug(
                    "Switching to BRIGHT mode: lux=%.1f > %d",
                    current_lux,
                    high_threshold,
                )
        # Currently in BRIGHT mode
        else:
            # Stay bright unless lux falls below LOW threshold
            if current_lux <= low_threshold:
                self._brightness_mode_is_dim = True
                _LOGGER.debug(
                    "Switching to DIM mode: lux=%.1f < %d",
                    current_lux,
                    low_threshold,
                )

        return self._brightness_mode_is_dim

    # ========================================================================
    # Data Management
    # ========================================================================

    # ========================================================================
    # Event Tracking (for diagnostics)
    # ========================================================================

    def _log_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Log an event for diagnostics."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            **details,
        }
        self._events.append(event)

        # Keep only last N events
        if len(self._events) > self._max_events:
            self._events.pop(0)

        _LOGGER.debug("Event logged: %s - %s", event_type, details)

    def _log_transition(self, from_state: str, to_state: str, reason: str) -> None:
        """Log a state transition."""
        self._last_transition_reason = reason
        self._last_transition_time = datetime.now()
        self._log_event(
            "state_transition",
            {
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
            },
        )

    def get_diagnostic_data(self) -> dict[str, Any]:
        """Get diagnostic data for sensor."""
        context = self._get_context()
        timer_info = self.timer_manager.get_info()
        light_info = self.light_controller.get_info()

        return {
            "current_state": self.state_machine.current_state,
            "motion_active": context.get("motion_active", False),
            "is_dark_inside": context.get("is_dark_inside", True),
            "is_house_active": context.get("is_house_active", False),
            "motion_activation_enabled": self.motion_activation,
            "timers": timer_info.get("timers", {}),
            "lights_on": light_info.get("lights_on", 0),
            "total_lights": light_info.get("total_lights", 0),
            "recent_events": list(self._events),
            "last_transition_reason": self._last_transition_reason,
            "last_transition_time": (
                self._last_transition_time.isoformat()
                if self._last_transition_time
                else None
            ),
        }

    # ========================================================================
    # Data Update
    # ========================================================================

    def _update_data(self) -> None:
        """Update coordinator data."""
        timer_info = self.timer_manager.get_info()
        active_timers = timer_info.get("active_timers", 0)

        self.data = {
            "current_state": self.state_machine.current_state,
            "timer_active": active_timers > 0,
            "timer_type": (
                list(timer_info.get("timers", {}).keys())[0]
                if active_timers > 0
                else None
            ),
            "lights_on": self.light_controller.get_info().get("lights_on", 0),
            "motion_activation": self.motion_activation,
        }

        self.async_update_listeners()

    # ========================================================================
    # Cleanup
    # ========================================================================

    def _schedule_periodic_cleanup(self) -> None:
        """Schedule periodic cleanup of old context IDs.

        This runs every hour to prevent unbounded memory growth from context tracking.
        """

        def cleanup_task() -> None:
            """Perform cleanup and reschedule."""
            _LOGGER.debug("Performing periodic context cleanup")
            self.light_controller.cleanup_old_contexts()
            # Reschedule for next hour
            self._cleanup_handle = self.hass.loop.call_later(3600, cleanup_task)

        # Schedule first cleanup in 1 hour
        self._cleanup_handle = self.hass.loop.call_later(3600, cleanup_task)

    async def async_refresh_light_tracking(self) -> None:
        """Refresh light state tracking (called by service)."""
        _LOGGER.info("Refreshing light state tracking")
        self.light_controller.refresh_all_states()
        self._update_data()

    def async_cleanup_listeners(self) -> None:
        """Clean up listeners."""
        # Cancel periodic cleanup task
        if self._cleanup_handle is not None:
            self._cleanup_handle.cancel()
            self._cleanup_handle = None

        # Cancel all timers
        self.timer_manager.cancel_all_timers()

        # Clean up event listeners
        for unsub in self._unsubscribers:
            unsub()
        self._unsubscribers.clear()
        self.trigger_manager.cleanup_all()
        self.timer_manager.cancel_all_timers()
        # Final cleanup of context tracking
        self.light_controller.cleanup_old_contexts()

    # ========================================================================
    # Properties for compatibility
    # ========================================================================

    @property
    def current_state(self) -> str:
        return self.state_machine.current_state

    @property
    def time_until_action(self) -> int | None:
        active_timers = self.timer_manager.get_active_timers()
        if active_timers:
            return active_timers[0].remaining_seconds
        return None

    @property
    def motion_entity(self) -> str:
        return self.motion_entities[0] if self.motion_entities else ""

    @property
    def lights(self) -> list[str]:
        """Return list of all configured light entity IDs."""
        return list(self._lights)

    @property
    def is_motion_activation_enabled(self) -> bool:
        return self.motion_activation

    @property
    def no_motion_wait_seconds(self) -> int:
        return self._no_motion_wait

    # These properties are kept for backward compatibility and sensor access
    # The actual values are now stored in self.brightness_active and self.brightness_inactive
    # which are loaded from CONF_BRIGHTNESS_ACTIVE and CONF_BRIGHTNESS_INACTIVE
