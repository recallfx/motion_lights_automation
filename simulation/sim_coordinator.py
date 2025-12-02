"""Simulation coordinator for motion lights automation.

This module wraps the real coordinator logic for standalone operation
without Home Assistant dependencies. Uses shared base modules for
state machine logic.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

# Import from shared base modules
from custom_components.motion_lights_automation.base_state_machine import (
    BaseStateMachine,
    StateTransitionEvent,
    STATE_IDLE,
    STATE_AUTO,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_MOTION_AUTO,
    STATE_MOTION_MANUAL,
    STATE_OVERRIDDEN,
)
from custom_components.motion_lights_automation.base_timer_manager import (
    BaseTimer,
    BaseTimerManager,
    TimerType,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class SimLight:
    """Simulated light entity."""

    entity_id: str
    is_on: bool = False
    brightness_pct: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "is_on": self.is_on,
            "brightness_pct": self.brightness_pct,
        }


@dataclass
class SimSensor:
    """Simulated sensor entity."""

    entity_id: str
    state: bool = False
    sensor_type: str = "motion"
    last_changed: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "state": self.state,
            "type": self.sensor_type,
            "last_changed": self.last_changed,
        }


class SimTimer(BaseTimer):
    """Simulation timer using asyncio.

    Extends BaseTimer with asyncio-based timing.
    """

    def __init__(
        self,
        timer_type: TimerType,
        callback: Callable[[], Any],
        duration: int,
        name: str | None = None,
    ):
        """Initialize timer."""
        super().__init__(timer_type, duration, callback, name)
        self._task: asyncio.Task | None = None

    def _get_current_time(self) -> datetime:
        """Get current time as datetime."""
        return datetime.fromtimestamp(time.time())

    def start(self) -> None:
        """Start the timer."""
        self._do_start()

        async def timer_task():
            await asyncio.sleep(self.duration)
            await self._async_expire()

        self._task = asyncio.create_task(timer_task())

    def cancel(self) -> None:
        """Cancel the timer."""
        self._do_cancel()
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize timer state."""
        return {
            "name": self.name,
            "type": self.timer_type.value,
            "duration": self.duration,
            "remaining": self.remaining_seconds,
            "remaining_seconds": self.remaining_seconds,
            "active": self.is_active,
            "is_active": self.is_active,
        }


class SimTimerManager(BaseTimerManager):
    """Timer manager for simulation using asyncio."""

    def __init__(self, on_timer_expired: Callable[[str], Any] | None = None):
        """Initialize timer manager."""
        super().__init__()
        self._on_timer_expired = on_timer_expired

    def create_timer(
        self,
        timer_type: TimerType,
        callback: Callable,
        duration: int | None = None,
        name: str | None = None,
    ) -> BaseTimer:
        """Create a simulation timer."""
        actual_duration = duration or self._default_durations.get(timer_type, 120)
        return SimTimer(timer_type, callback, actual_duration, name)

    def start_timer(
        self,
        name: str,
        timer_type: TimerType,
        duration: int,
    ) -> BaseTimer:
        """Start a timer with automatic callback wiring."""

        def on_expire(timer_name: str):
            if self._on_timer_expired:
                return self._on_timer_expired(timer_name)

        return super().start_timer(name, timer_type, on_expire, duration)


@dataclass
class Snapshot:
    """State snapshot for history/replay."""

    timestamp: float
    event_type: str
    description: str
    state: str
    lights: dict[str, dict]
    sensors: dict[str, dict]
    timers: dict[str, dict]


@dataclass
class SimConfig:
    """Simulation configuration."""

    lights: list[str] = field(default_factory=lambda: ["light.room"])
    motion_sensors: list[str] = field(default_factory=lambda: ["binary_sensor.motion"])
    override_switch: str | None = "switch.override"
    no_motion_wait: int = 300  # 5 minutes
    extended_timeout: int = 1200  # 20 minutes
    motion_delay: int = 0
    motion_activation: bool = True
    brightness_active: int = 80
    brightness_inactive: int = 10
    is_house_active: bool = True
    is_dark_inside: bool = True


class SimMotionCoordinator:
    """Simulation coordinator for standalone operation.

    Uses shared core module for state machine logic.
    Uses a custom listener pattern for WebSocket updates.
    """

    def __init__(self, config: SimConfig | None = None):
        """Initialize the simulation coordinator."""
        self.config = config or SimConfig()
        self._listeners: list[Callable[[], Any]] = []

        # State machine from core module
        self._state_machine = BaseStateMachine()
        self._state_entered_at: float = time.time()

        # Timer manager
        self._timer_manager = SimTimerManager(on_timer_expired=self._on_timer_expired)

        # Entities
        self._lights: dict[str, SimLight] = {}
        self._sensors: dict[str, SimSensor] = {}
        self._override_active = False

        # History
        self._snapshots: list[Snapshot] = []
        self._max_snapshots = 1000

        # Event log (list of dicts with timestamp, message, type)
        self._event_log: list[dict] = []
        self._max_log_entries = 50

        # Track what triggered the last state change
        self._last_trigger: str | None = None

        # Initialize entities
        self._init_entities()

    @property
    def _current_state(self) -> str:
        """Get current state from state machine."""
        return self._state_machine.current_state

    @property
    def _previous_state(self) -> str | None:
        """Get previous state from state machine."""
        return self._state_machine.previous_state

    @property
    def _timers(self) -> dict[str, SimTimer]:
        """Get active timers from timer manager."""
        return {
            name: timer
            for name, timer in self._timer_manager._timers.items()
            if isinstance(timer, SimTimer) and timer.is_active
        }

    def _init_entities(self) -> None:
        """Initialize simulated entities."""
        for light_id in self.config.lights:
            self._lights[light_id] = SimLight(entity_id=light_id)

        for sensor_id in self.config.motion_sensors:
            self._sensors[sensor_id] = SimSensor(
                entity_id=sensor_id, sensor_type="motion"
            )

        # Add override switch as a sensor
        if self.config.override_switch:
            self._sensors[self.config.override_switch] = SimSensor(
                entity_id=self.config.override_switch, sensor_type="override"
            )

    # ========================================================================
    # Listener Pattern
    # ========================================================================

    def async_add_listener(self, callback: Callable[[], Any]) -> Callable[[], None]:
        """Register for state change notifications.

        Returns:
            Callable to remove the listener
        """
        self._listeners.append(callback)
        return lambda: self._listeners.remove(callback)

    def _notify_listeners(self) -> None:
        """Trigger all registered listeners."""
        for callback in self._listeners:
            try:
                result = callback()
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as err:
                _LOGGER.error("Error in listener callback: %s", err)

    # ========================================================================
    # State Machine (delegates to BaseStateMachine)
    # ========================================================================

    def _transition(
        self, event: StateTransitionEvent, target_state: str | None = None
    ) -> bool:
        """Attempt state transition using core state machine."""
        old_state = self._current_state

        # Use state machine's transition method
        if event == StateTransitionEvent.OVERRIDE_OFF and target_state:
            # Special case for override off with explicit target
            self._state_machine._current_state = target_state
            self._state_machine._previous_state = old_state
            success = True
        else:
            success = self._state_machine.transition(event)

        if success and self._current_state != old_state:
            self._state_entered_at = time.time()
            self._log_event(
                f"State: {old_state} → {self._current_state} ({event.value})",
                "transition",
            )
            self._record_snapshot(
                event.value, f"Transition: {old_state} → {self._current_state}"
            )

            # Handle state entry actions
            self._on_enter_state(self._current_state, old_state, event)
            self._notify_listeners()

        return success

    def _on_enter_state(
        self, state: str, from_state: str, event: StateTransitionEvent
    ) -> None:
        """Handle state entry actions."""
        if state == STATE_MOTION_AUTO:
            self._turn_on_lights()
        elif state == STATE_AUTO:
            self._start_timer("motion", TimerType.MOTION, self.config.no_motion_wait)
        elif state == STATE_MANUAL:
            self._cancel_timer("motion")
            self._start_timer(
                "extended", TimerType.EXTENDED, self.config.extended_timeout
            )
        elif state == STATE_MANUAL_OFF:
            self._cancel_timer("motion")
            self._start_timer(
                "extended", TimerType.EXTENDED, self.config.extended_timeout
            )
        elif state == STATE_IDLE:
            self._turn_off_lights()
        elif state == STATE_OVERRIDDEN:
            self._cancel_all_timers()

    # ========================================================================
    # Timer Management (delegates to SimTimerManager)
    # ========================================================================

    def _start_timer(self, name: str, timer_type: TimerType, duration: int) -> None:
        """Start a timer using timer manager."""
        self._timer_manager.start_timer(name, timer_type, duration)

    def _cancel_timer(self, name: str) -> bool:
        """Cancel a specific timer."""
        return self._timer_manager.cancel_timer(name)

    def _cancel_all_timers(self) -> None:
        """Cancel all active timers."""
        self._timer_manager.cancel_all_timers()

    def _on_timer_expired(self, timer_name: str) -> None:
        """Handle timer expiration callback."""
        _LOGGER.info("Timer '%s' expired", timer_name)

        valid_states = (STATE_AUTO, STATE_MANUAL, STATE_MANUAL_OFF)
        if self._current_state not in valid_states:
            _LOGGER.debug(
                "Timer expired but state %s doesn't accept it", self._current_state
            )
            return

        self._last_trigger = f"{timer_name}_timer"
        self._log_event(f"Timer expired: {timer_name}", "timer")
        self._transition(StateTransitionEvent.TIMER_EXPIRED)

    # ========================================================================
    # Light Control
    # ========================================================================

    def _turn_on_lights(self) -> None:
        """Turn on all lights."""
        if not self.config.is_dark_inside:
            _LOGGER.debug("Skipping light turn on - not dark inside")
            return

        brightness = (
            self.config.brightness_active
            if self.config.is_house_active
            else self.config.brightness_inactive
        )

        if brightness <= 0:
            return

        for light in self._lights.values():
            light.is_on = True
            light.brightness_pct = brightness

        _LOGGER.debug("Turned on lights at %d%%", brightness)

    def _turn_off_lights(self) -> None:
        """Turn off all lights."""
        for light in self._lights.values():
            light.is_on = False
            light.brightness_pct = 0
        _LOGGER.debug("Turned off lights")

    def _any_lights_on(self) -> bool:
        """Check if any lights are on."""
        return any(light.is_on for light in self._lights.values())

    # ========================================================================
    # Sensor Events (called from server)
    # ========================================================================

    async def process_sensor_event(self, entity_id: str, state: bool) -> None:
        """Process a sensor event from the simulation UI."""
        _LOGGER.info("Sensor event: %s = %s", entity_id, state)

        # Check if this is the override switch
        if entity_id == self.config.override_switch:
            await self._process_override_event(state)
            return

        # Check if it's a motion sensor
        if entity_id in self._sensors:
            sensor = self._sensors[entity_id]
            old_state = sensor.state
            sensor.state = state
            sensor.last_changed = time.time()

            # Store trigger context for transition logging
            self._last_trigger = entity_id
            short_name = entity_id.split(".")[-1].replace("_", " ").title()

            self._log_event(f"{short_name}: {'ON' if state else 'OFF'}", "sensor")

            if state and not old_state:
                # Motion detected
                self._handle_motion_on()
            elif not state and old_state:
                # Motion cleared - check if ALL sensors are off
                if not self._any_motion_active():
                    self._handle_motion_off()

            self._notify_listeners()

    async def _process_override_event(self, state: bool) -> None:
        """Process override switch event."""
        old_state = self._override_active
        self._override_active = state

        # Update sensor state too
        if self.config.override_switch and self.config.override_switch in self._sensors:
            self._sensors[self.config.override_switch].state = state

        self._last_trigger = "override"
        self._log_event(f"Override: {'ON' if state else 'OFF'}", "sensor")

        if state and not old_state:
            self._cancel_all_timers()
            self._transition(StateTransitionEvent.OVERRIDE_ON)
        elif not state and old_state:
            if self._any_lights_on():
                self._transition(
                    StateTransitionEvent.OVERRIDE_OFF, target_state=STATE_MANUAL
                )
            else:
                self._transition(
                    StateTransitionEvent.OVERRIDE_OFF, target_state=STATE_IDLE
                )

    def _any_motion_active(self) -> bool:
        """Check if any motion sensor is active."""
        return any(sensor.state for sensor in self._sensors.values())

    def _handle_motion_on(self) -> None:
        """Handle motion detected."""
        if not self.config.motion_activation:
            # Still reset timers even if motion activation is disabled
            if self._current_state in (STATE_MANUAL, STATE_AUTO, STATE_MANUAL_OFF):
                self._cancel_timer("extended")
                self._start_timer(
                    "extended", TimerType.EXTENDED, self.config.extended_timeout
                )
            return

        if self._current_state == STATE_MANUAL:
            self._transition(StateTransitionEvent.MOTION_ON)
        elif self._current_state == STATE_AUTO:
            self._cancel_all_timers()
            self._transition(StateTransitionEvent.MOTION_ON)
        elif self._current_state in (STATE_IDLE, STATE_MANUAL_OFF):
            if self.config.motion_delay > 0:
                self._start_timer(
                    "motion_delay", TimerType.CUSTOM, self.config.motion_delay
                )
            else:
                self._transition(StateTransitionEvent.MOTION_ON)

    def _handle_motion_off(self) -> None:
        """Handle motion cleared."""
        self._cancel_timer("motion_delay")

        if self._current_state == STATE_MOTION_AUTO:
            self._transition(StateTransitionEvent.MOTION_OFF)
        elif self._current_state == STATE_MOTION_MANUAL:
            self._transition(StateTransitionEvent.MOTION_OFF)

    # ========================================================================
    # Light Control Events (called from server)
    # ========================================================================

    async def process_light_event(
        self, entity_id: str, state: bool, brightness: int = 0
    ) -> None:
        """Process a light control event (manual intervention)."""
        if entity_id not in self._lights:
            return

        light = self._lights[entity_id]
        old_is_on = light.is_on

        light.is_on = state
        light.brightness_pct = brightness if state else 0

        # Store trigger context for transition logging
        self._last_trigger = entity_id
        short_name = entity_id.split(".")[-1].replace("_", " ").title()

        self._log_event(f"{short_name}: {'ON' if state else 'OFF'} (manual)", "light")

        # Detect manual intervention
        if state and not old_is_on:
            # Light turned on manually
            self._handle_manual_intervention_on()
        elif not state and old_is_on:
            # Light turned off manually
            if not self._any_lights_on():
                self._handle_manual_intervention_off()

        self._notify_listeners()

    def _handle_manual_intervention_on(self) -> None:
        """Handle manual light turn on."""
        if self._current_state in (
            STATE_IDLE,
            STATE_AUTO,
            STATE_MOTION_AUTO,
            STATE_MANUAL_OFF,
        ):
            self._transition(StateTransitionEvent.MANUAL_INTERVENTION)

    def _handle_manual_intervention_off(self) -> None:
        """Handle manual light turn off (all lights off)."""
        if self._current_state in (
            STATE_AUTO,
            STATE_MANUAL,
            STATE_MOTION_AUTO,
            STATE_MOTION_MANUAL,
        ):
            self._transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION)

    # ========================================================================
    # Configuration Changes
    # ========================================================================

    def set_house_active(self, active: bool) -> None:
        """Set house active state."""
        self.config.is_house_active = active
        self._log_event(f"House active: {active}")

        # Adjust brightness of currently on lights
        if self._any_lights_on():
            brightness = (
                self.config.brightness_active
                if active
                else self.config.brightness_inactive
            )
            for light in self._lights.values():
                if light.is_on:
                    light.brightness_pct = brightness

        self._notify_listeners()

    def set_dark_inside(self, dark: bool) -> None:
        """Set ambient light state."""
        old_dark = self.config.is_dark_inside
        self.config.is_dark_inside = dark
        self._log_event(f"Dark inside: {dark}")

        # If it became bright, turn off auto lights
        if old_dark and not dark:
            if self._current_state in (STATE_AUTO, STATE_MOTION_AUTO):
                self._cancel_all_timers()
                self._turn_off_lights()
                self._transition(StateTransitionEvent.LIGHTS_ALL_OFF)

        # If it became dark and motion is active, turn on lights
        elif not old_dark and dark:
            if self._any_motion_active() and self.config.motion_activation:
                if self._current_state in (STATE_IDLE, STATE_MANUAL_OFF):
                    self._transition(StateTransitionEvent.MOTION_ON)

        self._notify_listeners()

    def set_motion_activation(self, enabled: bool) -> None:
        """Enable/disable motion activation."""
        self.config.motion_activation = enabled
        self._log_event(f"Motion activation: {enabled}")
        self._notify_listeners()

    # ========================================================================
    # History / Snapshots
    # ========================================================================

    def _record_snapshot(self, event_type: str, description: str) -> None:
        """Record a state snapshot."""
        snapshot = Snapshot(
            timestamp=time.time(),
            event_type=event_type,
            description=description,
            state=self._current_state,
            lights={lid: light.to_dict() for lid, light in self._lights.items()},
            sensors={sid: s.to_dict() for sid, s in self._sensors.items()},
            timers={tid: t.to_dict() for tid, t in self._timers.items()},
        )
        self._snapshots.append(snapshot)

        if len(self._snapshots) > self._max_snapshots:
            self._snapshots.pop(0)

    def get_history(self) -> list[dict]:
        """Get history snapshots for API."""
        return [
            {
                "timestamp": s.timestamp,
                "event_type": s.event_type,
                "description": s.description,
                "state": s.state,
                "lights": s.lights,
                "sensors": s.sensors,
                "timers": s.timers,
            }
            for s in self._snapshots
        ]

    def _log_event(self, message: str, event_type: str = "info") -> None:
        """Log an event message."""
        entry = {
            "timestamp": datetime.fromtimestamp(time.time()).isoformat(),
            "message": message,
            "type": event_type,
        }
        self._event_log.append(entry)

        if len(self._event_log) > self._max_log_entries:
            self._event_log.pop(0)

        _LOGGER.info(message)

    # ========================================================================
    # State Serialization
    # ========================================================================

    def get_simulation_state(self) -> dict[str, Any]:
        """Return JSON-serializable state for WebSocket."""
        return {
            "current_state": self._current_state,
            "previous_state": self._previous_state,
            "time_in_state": int(time.time() - self._state_entered_at),
            "lights": {lid: light.to_dict() for lid, light in self._lights.items()},
            "sensors": {sid: s.to_dict() for sid, s in self._sensors.items()},
            "timers": {tid: t.to_dict() for tid, t in self._timers.items()},
            "override_active": self._override_active,
            "config": {
                "motion_activation": self.config.motion_activation,
                "is_house_active": self.config.is_house_active,
                "is_dark_inside": self.config.is_dark_inside,
                "no_motion_wait": self.config.no_motion_wait,
                "extended_timeout": self.config.extended_timeout,
                "brightness_active": self.config.brightness_active,
                "brightness_inactive": self.config.brightness_inactive,
            },
            "event_log": list(self._event_log),
            "history_count": len(self._snapshots),
            "timestamp": time.time(),
        }

    def reset(self) -> None:
        """Reset the simulation to initial state."""
        self._cancel_all_timers()

        for light in self._lights.values():
            light.is_on = False
            light.brightness_pct = 0

        for sensor in self._sensors.values():
            sensor.state = False

        self._override_active = False

        # Reset state machine
        self._state_machine._current_state = STATE_IDLE
        self._state_machine._previous_state = None
        self._state_entered_at = time.time()

        self._snapshots.clear()
        self._event_log.clear()

        self._log_event("Simulation reset")
        self._notify_listeners()
