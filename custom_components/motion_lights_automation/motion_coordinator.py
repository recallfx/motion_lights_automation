"""Motion Lights Coordinator using modular architecture."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BACKGROUND_LIGHT,
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_CEILING_LIGHT,
    CONF_DARK_OUTSIDE,
    CONF_EXTENDED_TIMEOUT,
    CONF_FEATURE_LIGHT,
    CONF_HOUSE_ACTIVE,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
    DEFAULT_BRIGHTNESS_ACTIVE,
    DEFAULT_BRIGHTNESS_INACTIVE,
    DEFAULT_EXTENDED_TIMEOUT,
    DEFAULT_MOTION_ACTIVATION,
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

from .state_machine import MotionLightsStateMachine, StateTransitionEvent
from .timer_manager import TimerManager, TimerType
from .light_controller import (
    LightController,
    TimeOfDayBrightnessStrategy,
    TimeOfDayLightSelectionStrategy,
)
from .triggers import TriggerManager, MotionTrigger, OverrideTrigger
from .manual_detection import ManualInterventionDetector, BrightnessThresholdStrategy

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
        
        # Light controller with strategies
        light_groups = {
            "ceiling": self.ceiling_lights,
            "background": self.background_lights,
            "feature": self.feature_lights,
        }
        self.light_controller = LightController(
            hass,
            light_groups,
            brightness_strategy=TimeOfDayBrightnessStrategy(
                active_brightness=self.brightness_active,
                inactive_brightness=self.brightness_inactive,
            ),
            light_selection_strategy=TimeOfDayLightSelectionStrategy(),
        )
        
        # Manual intervention detector
        self.manual_detector = ManualInterventionDetector()
        brightness_strategy = BrightnessThresholdStrategy()
        # ManualInterventionDetector uses set_strategy to configure the strategy
        self.manual_detector.set_strategy(brightness_strategy)
        
        # Set timer durations
        self.timer_manager.set_default_duration(TimerType.MOTION, self._no_motion_wait)
        self.timer_manager.set_default_duration(TimerType.EXTENDED, self.extended_timeout)
        
        # Tracking
        self._unsubscribers: list = []
        self.data = {}

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
        self.motion_activation = data.get(CONF_MOTION_ACTIVATION, DEFAULT_MOTION_ACTIVATION)
        self._no_motion_wait = data.get(CONF_NO_MOTION_WAIT, DEFAULT_NO_MOTION_WAIT)
        self.extended_timeout = data.get(CONF_EXTENDED_TIMEOUT, DEFAULT_EXTENDED_TIMEOUT)
        
        # Entities
        self.motion_entities = _as_list(data.get(CONF_MOTION_ENTITY))
        override_cfg = data.get(CONF_OVERRIDE_SWITCH)
        if isinstance(override_cfg, (list, tuple, set)):
            override_list = [str(v) for v in override_cfg if v]
            self.override_switch = override_list[0] if override_list else None
        else:
            self.override_switch = str(override_cfg) if override_cfg else None
        
        self.dark_outside = data.get(CONF_DARK_OUTSIDE)
        self.house_active = data.get(CONF_HOUSE_ACTIVE)
        self.brightness_active = data.get(CONF_BRIGHTNESS_ACTIVE, DEFAULT_BRIGHTNESS_ACTIVE)
        self.brightness_inactive = data.get(CONF_BRIGHTNESS_INACTIVE, DEFAULT_BRIGHTNESS_INACTIVE)
        
        # Lights
        self.background_lights = _as_list(data.get(CONF_BACKGROUND_LIGHT))
        self.feature_lights = _as_list(data.get(CONF_FEATURE_LIGHT))
        self.ceiling_lights = _as_list(data.get(CONF_CEILING_LIGHT))

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
            motion_trigger = MotionTrigger(self.hass, {
                "entity_ids": self.motion_entities,
                "enabled": self.motion_activation,
            })
            motion_trigger.on_activated(self._handle_motion_on)
            motion_trigger.on_deactivated(self._handle_motion_off)
            self.trigger_manager.add_trigger("motion", motion_trigger)
        
        # Set up override trigger
        if self.override_switch:
            override_trigger = OverrideTrigger(self.hass, {"entity_id": self.override_switch})
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
        active_timers = self.timer_manager._timers.__len__() if hasattr(self.timer_manager, '_timers') else 0
        
        _LOGGER.info(
            "Motion Lights Automation initialized: %.2fs | Lights: %d | Timers: %d | "
            "Motion activation: %s | Override: %s | Dark outside: %s",
            elapsed, total_lights, active_timers,
            self.motion_activation, bool(self.override_switch), bool(self.dark_outside)
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
            
            if not self.motion_activation:
                # When motion_activation is disabled, motion doesn't turn on lights.
                # However, if lights are already on (manually), restart the timer.
                if self.light_controller.any_lights_on():
                    _LOGGER.debug("Motion detected with motion_activation=False; restarting timer")
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
                self.state_machine.transition(StateTransitionEvent.MOTION_ON)
        except Exception:
            _LOGGER.exception("Error in motion ON handler")

    def _handle_motion_off(self) -> None:
        """Handle motion cleared."""
        try:
            _LOGGER.info("Motion OFF")
            
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
            _LOGGER.info("Override ON - current state: %s", self.state_machine.current_state)
            self.timer_manager.cancel_all_timers()
            result = self.state_machine.transition(StateTransitionEvent.OVERRIDE_ON)
            _LOGGER.info("Override ON transition result: %s, new state: %s", result, self.state_machine.current_state)
            self._update_data()
        except Exception:
            _LOGGER.exception("Error in override ON handler")

    def _handle_override_off(self) -> None:
        """Handle override deactivated."""
        try:
            _LOGGER.info("Override OFF - current state: %s", self.state_machine.current_state)
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
            if not self.light_controller.is_integration_context(new_state.context):
                is_manual = self.manual_detector.check_intervention(
                    entity_id, old_state, new_state, new_state.context
                )
                
                if is_manual:
                    self._handle_manual_intervention(entity_id, old_state, new_state)
            
            # Check if all lights are off
            if not self.light_controller.any_lights_on():
                if self.state_machine.current_state not in (STATE_OVERRIDDEN, STATE_MANUAL_OFF):
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
            entity_id, change_type, brightness, current
        )
        
        if current == STATE_MOTION_AUTO:
            self.state_machine.transition(StateTransitionEvent.MANUAL_INTERVENTION)
        elif current == STATE_MOTION_MANUAL:
            # Already in manual mode during motion, log but don't transition
            # However, restart any active timer to extend the grace period
            _LOGGER.debug("Manual change during MOTION_MANUAL state - already tracking manually, no timer to restart")
        elif current == STATE_MANUAL:
            # User is actively adjusting lights in MANUAL state
            if new_state.state == "off" and old_state.state == "on":
                # User turned off a light - check if all lights are off
                if not self.light_controller.any_lights_on():
                    # All lights turned off, transition to MANUAL_OFF
                    _LOGGER.info("User turned off all lights in MANUAL state - transitioning to MANUAL_OFF")
                    self.state_machine.transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION)
                else:
                    # Some lights still on, restart timer
                    _LOGGER.info("User turned off a light in MANUAL state - restarting extended timer")
                    self.timer_manager.cancel_timer("extended")
                    self.timer_manager.start_timer(
                        "extended",
                        TimerType.EXTENDED,
                        self._async_timer_expired,
                    )
            else:
                # Brightness adjustment or turning on more lights - restart the extended timer
                _LOGGER.info("Manual adjustment in MANUAL state - restarting extended timer")
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
                    _LOGGER.info("User turned off all lights in AUTO state - transitioning to MANUAL_OFF")
                    self.state_machine.transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION)
                else:
                    # Some lights still on, transition to MANUAL
                    _LOGGER.info("User turned off a light in AUTO state but some remain on - transitioning to MANUAL")
                    self.state_machine.transition(StateTransitionEvent.MANUAL_INTERVENTION)
            else:
                self.state_machine.transition(StateTransitionEvent.MANUAL_INTERVENTION)
        elif current == STATE_MANUAL_OFF:
            # User manually turned off lights, but now they're adjusting them again
            # This means they're still active, so transition to MANUAL state
            if new_state.state == "on" or (new_state.state == "on" and old_state.state == "on"):
                _LOGGER.info("Manual adjustment in MANUAL_OFF state - user is active, transitioning to MANUAL")
                self.state_machine.transition(StateTransitionEvent.MANUAL_INTERVENTION)
            else:
                # Another light turned off - just restart the extended timer
                _LOGGER.info("Additional manual OFF in MANUAL_OFF state - restarting extended timer")
                self.timer_manager.cancel_timer("extended")
                self.timer_manager.start_timer(
                    "extended",
                    TimerType.EXTENDED,
                    self._async_timer_expired,
                )
        elif current == STATE_IDLE:
            if new_state.state == "on":
                self.state_machine.transition(StateTransitionEvent.MANUAL_INTERVENTION)

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
        _LOGGER.debug("Entering MANUAL_OFF state - cancelling motion timer, starting extended timer")
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
        _LOGGER.info("State transition: %s -> %s (event: %s)", old_state, new_state, event.value)
        self._update_data()

    # ========================================================================
    # Timer Callbacks
    # ========================================================================

    async def _async_timer_expired(self, timer_id: str = None) -> None:
        """Timer expired - transition to idle."""
        _LOGGER.info("Timer expired: %s", timer_id)
        self.state_machine.transition(StateTransitionEvent.TIMER_EXPIRED)

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
        # Determine if house is inactive (use dim brightness)
        # Priority: house_active switch > dark_outside sensor > default to active
        is_inactive = False
        
        if self.house_active:
            # Priority 1: Check house_active switch
            house_state = self.hass.states.get(self.house_active)
            if house_state is None:
                _LOGGER.warning(
                    "house_active entity '%s' not found; falling back to dark_outside or active mode",
                    self.house_active,
                )
            else:
                # If house_active is OFF, house is inactive (use dim brightness)
                is_inactive = house_state.state == "off"
        elif self.dark_outside:
            # Priority 2: Check dark_outside sensor
            dark_state = self.hass.states.get(self.dark_outside)
            if dark_state is None:
                _LOGGER.warning(
                    "dark_outside entity '%s' not found; falling back to active brightness",
                    self.dark_outside,
                )
            else:
                # If it's dark outside, house is inactive (use dim brightness)
                is_inactive = dark_state.state == "on"
        # Else: Default to active mode (is_inactive = False)
        
        motion_trigger = self.trigger_manager.get_trigger("motion")
        motion_active = motion_trigger.is_active() if motion_trigger else False
        
        # Return dict-like context that strategies can use
        return {
            "time_of_day": "inactive" if is_inactive else "active",
            "is_dark": is_inactive,  # Keep for backward compatibility
            "is_night": is_inactive,  # Keep for backward compatibility
            "is_inactive": is_inactive,
            "motion_active": motion_active,
            "current_state": self.state_machine.current_state,
            "all_lights": self.light_controller.get_all_lights(),
        }

    # ========================================================================
    # Data Management
    # ========================================================================

    def _update_data(self) -> None:
        """Update coordinator data."""
        timer_info = self.timer_manager.get_info()
        active_timers = timer_info.get("active_timers", 0)
        
        self.data = {
            "current_state": self.state_machine.current_state,
            "timer_active": active_timers > 0,
            "timer_type": list(timer_info.get("timers", {}).keys())[0] if active_timers > 0 else None,
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
            self.hass.loop.call_later(3600, cleanup_task)
        
        # Schedule first cleanup in 1 hour
        self.hass.loop.call_later(3600, cleanup_task)

    async def async_refresh_light_tracking(self) -> None:
        """Refresh light state tracking (called by service)."""
        _LOGGER.info("Refreshing light state tracking")
        self.light_controller.refresh_all_states()
        self._update_data()

    def async_cleanup_listeners(self) -> None:
        """Clean up listeners."""
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
    def background_light(self) -> str:
        return self.background_lights[0] if self.background_lights else ""

    @property
    def feature_light(self) -> str:
        return self.feature_lights[0] if self.feature_lights else ""

    @property
    def ceiling_light(self) -> str:
        return self.ceiling_lights[0] if self.ceiling_lights else ""

    @property
    def is_motion_activation_enabled(self) -> bool:
        return self.motion_activation

    @property
    def no_motion_wait_seconds(self) -> int:
        return self._no_motion_wait

    # These properties are kept for backward compatibility and sensor access
    # The actual values are now stored in self.brightness_active and self.brightness_inactive
    # which are loaded from CONF_BRIGHTNESS_ACTIVE and CONF_BRIGHTNESS_INACTIVE
