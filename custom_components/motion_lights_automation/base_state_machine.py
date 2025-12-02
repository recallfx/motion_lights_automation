"""Base state machine for motion lights automation.

This module provides a clean state machine implementation that can be used
by both the Home Assistant integration and standalone simulation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)

# State constants
STATE_OVERRIDDEN = "overridden"
STATE_IDLE = "idle"
STATE_MOTION_AUTO = "motion-auto"
STATE_MOTION_MANUAL = "motion-manual"
STATE_AUTO = "auto"
STATE_MANUAL = "manual"
STATE_MANUAL_OFF = "manual-off"


class StateTransitionEvent(Enum):
    """Events that can trigger state transitions."""

    MOTION_ON = "motion_on"
    MOTION_OFF = "motion_off"
    OVERRIDE_ON = "override_on"
    OVERRIDE_OFF = "override_off"
    MANUAL_INTERVENTION = "manual_intervention"
    MANUAL_OFF_INTERVENTION = "manual_off_intervention"
    TIMER_EXPIRED = "timer_expired"
    LIGHTS_ALL_OFF = "lights_all_off"


@dataclass
class StateTransition:
    """Represents a state transition."""

    from_state: str
    to_state: str
    event: StateTransitionEvent
    condition: Callable[[], bool] | None = None
    action: Callable[[], None] | None = None


class BaseStateMachine:
    """State machine for motion lights automation.

    This class handles state transitions and maintains the current state.
    It's designed to be easily extended with new states and transitions.
    """

    def __init__(
        self,
        initial_state: str = STATE_IDLE,
        get_current_time: Callable[[], datetime] | None = None,
    ):
        """Initialize the state machine.

        Args:
            initial_state: The initial state of the machine
            get_current_time: Optional function to get current time (for testing/simulation)
        """
        self._current_state = initial_state
        self._previous_state: str | None = None
        self._get_current_time = get_current_time or self._default_get_time
        self._state_entered_at: datetime = self._get_current_time()
        self._transitions: dict[
            tuple[str, StateTransitionEvent], list[StateTransition]
        ] = {}
        self._state_entry_callbacks: dict[str, list[Callable]] = {}
        self._state_exit_callbacks: dict[str, list[Callable]] = {}
        self._transition_callbacks: list[
            Callable[[str, str, StateTransitionEvent], None]
        ] = []

        self._define_transitions()

    def _default_get_time(self) -> datetime:
        """Default time provider using datetime.now()."""
        return datetime.now()

    def _define_transitions(self) -> None:
        """Define valid state transitions.

        This method defines the core state machine logic. Each transition
        specifies the starting state, event, and target state.
        """
        # Motion ON transitions
        self._add_transition(
            STATE_IDLE, StateTransitionEvent.MOTION_ON, STATE_MOTION_AUTO
        )
        self._add_transition(
            STATE_AUTO, StateTransitionEvent.MOTION_ON, STATE_MOTION_AUTO
        )
        self._add_transition(
            STATE_MANUAL, StateTransitionEvent.MOTION_ON, STATE_MOTION_MANUAL
        )
        self._add_transition(
            STATE_MANUAL_OFF, StateTransitionEvent.MOTION_ON, STATE_MANUAL_OFF
        )  # Ignore

        # Motion OFF transitions
        self._add_transition(
            STATE_MOTION_AUTO, StateTransitionEvent.MOTION_OFF, STATE_AUTO
        )
        self._add_transition(
            STATE_MOTION_MANUAL, StateTransitionEvent.MOTION_OFF, STATE_MANUAL
        )

        # Override transitions
        self._add_transition(
            STATE_IDLE, StateTransitionEvent.OVERRIDE_ON, STATE_OVERRIDDEN
        )
        self._add_transition(
            STATE_AUTO, StateTransitionEvent.OVERRIDE_ON, STATE_OVERRIDDEN
        )
        self._add_transition(
            STATE_MANUAL, StateTransitionEvent.OVERRIDE_ON, STATE_OVERRIDDEN
        )
        self._add_transition(
            STATE_MOTION_AUTO, StateTransitionEvent.OVERRIDE_ON, STATE_OVERRIDDEN
        )
        self._add_transition(
            STATE_MOTION_MANUAL, StateTransitionEvent.OVERRIDE_ON, STATE_OVERRIDDEN
        )
        self._add_transition(
            STATE_MANUAL_OFF, StateTransitionEvent.OVERRIDE_ON, STATE_OVERRIDDEN
        )
        self._add_transition(
            STATE_OVERRIDDEN, StateTransitionEvent.OVERRIDE_ON, STATE_OVERRIDDEN
        )

        # Override OFF can go to MANUAL or IDLE depending on lights
        self._add_transition(
            STATE_OVERRIDDEN, StateTransitionEvent.OVERRIDE_OFF, STATE_MANUAL
        )
        self._add_transition(
            STATE_OVERRIDDEN, StateTransitionEvent.OVERRIDE_OFF, STATE_IDLE
        )

        # Manual intervention transitions
        self._add_transition(
            STATE_MOTION_AUTO,
            StateTransitionEvent.MANUAL_INTERVENTION,
            STATE_MOTION_MANUAL,
        )
        self._add_transition(
            STATE_AUTO, StateTransitionEvent.MANUAL_INTERVENTION, STATE_MANUAL
        )
        self._add_transition(
            STATE_IDLE, StateTransitionEvent.MANUAL_INTERVENTION, STATE_MANUAL
        )
        self._add_transition(
            STATE_MANUAL_OFF, StateTransitionEvent.MANUAL_INTERVENTION, STATE_MANUAL
        )

        # Manual OFF intervention
        self._add_transition(
            STATE_AUTO, StateTransitionEvent.MANUAL_OFF_INTERVENTION, STATE_MANUAL_OFF
        )
        self._add_transition(
            STATE_MANUAL, StateTransitionEvent.MANUAL_OFF_INTERVENTION, STATE_MANUAL_OFF
        )
        self._add_transition(
            STATE_MOTION_AUTO,
            StateTransitionEvent.MANUAL_OFF_INTERVENTION,
            STATE_MANUAL_OFF,
        )
        self._add_transition(
            STATE_MOTION_MANUAL,
            StateTransitionEvent.MANUAL_OFF_INTERVENTION,
            STATE_MANUAL_OFF,
        )

        # Timer expired transitions
        self._add_transition(STATE_AUTO, StateTransitionEvent.TIMER_EXPIRED, STATE_IDLE)
        self._add_transition(
            STATE_MANUAL, StateTransitionEvent.TIMER_EXPIRED, STATE_IDLE
        )
        self._add_transition(
            STATE_MANUAL_OFF, StateTransitionEvent.TIMER_EXPIRED, STATE_IDLE
        )

        # All lights off transitions
        self._add_transition(
            STATE_AUTO, StateTransitionEvent.LIGHTS_ALL_OFF, STATE_IDLE
        )
        self._add_transition(
            STATE_MANUAL, StateTransitionEvent.LIGHTS_ALL_OFF, STATE_IDLE
        )
        self._add_transition(
            STATE_MOTION_AUTO, StateTransitionEvent.LIGHTS_ALL_OFF, STATE_IDLE
        )
        self._add_transition(
            STATE_MOTION_MANUAL, StateTransitionEvent.LIGHTS_ALL_OFF, STATE_IDLE
        )

    def _add_transition(
        self,
        from_state: str,
        event: StateTransitionEvent,
        to_state: str,
        condition: Callable[[], bool] | None = None,
    ) -> None:
        """Add a valid state transition."""
        key = (from_state, event)
        if key not in self._transitions:
            self._transitions[key] = []
        self._transitions[key].append(
            StateTransition(from_state, to_state, event, condition)
        )

    def transition(self, event: StateTransitionEvent, **kwargs: Any) -> bool:
        """Attempt to transition based on an event.

        Args:
            event: The event triggering the transition
            **kwargs: Additional parameters (e.g., target_state for conditional transitions)

        Returns:
            True if transition occurred, False otherwise
        """
        key = (self._current_state, event)
        possible_transitions = self._transitions.get(key, [])

        if not possible_transitions:
            _LOGGER.debug(
                "No transition defined for state=%s, event=%s",
                self._current_state,
                event.value,
            )
            return False

        # Find a valid transition (check conditions if any)
        target_state = kwargs.get("target_state")
        for trans in possible_transitions:
            # If target_state specified, only consider matching transitions
            if target_state and trans.to_state != target_state:
                continue

            # Check condition if present
            if trans.condition and not trans.condition():
                continue

            # Execute the transition
            return self._execute_transition(trans)

        _LOGGER.debug(
            "No valid transition found for state=%s, event=%s (conditions not met)",
            self._current_state,
            event.value,
        )
        return False

    def _execute_transition(self, transition: StateTransition) -> bool:
        """Execute a state transition."""
        old_state = self._current_state
        new_state = transition.to_state

        # Don't transition if already in target state
        if old_state == new_state:
            return False

        _LOGGER.info(
            "State transition: %s -> %s (event: %s)",
            old_state,
            new_state,
            transition.event.value,
        )

        # Call exit callbacks for old state
        for callback in self._state_exit_callbacks.get(old_state, []):
            try:
                callback()
            except Exception as err:
                _LOGGER.error("Error in state exit callback: %s", err)

        # Update state
        self._previous_state = old_state
        self._current_state = new_state
        self._state_entered_at = self._get_current_time()

        # Call entry callbacks for new state
        for callback in self._state_entry_callbacks.get(new_state, []):
            try:
                callback()
            except Exception as err:
                _LOGGER.error("Error in state entry callback: %s", err)

        # Call transition callbacks
        for callback in self._transition_callbacks:
            try:
                callback(old_state, new_state, transition.event)
            except Exception as err:
                _LOGGER.error("Error in transition callback: %s", err)

        return True

    def force_state(self, state: str) -> None:
        """Force the state machine to a specific state (use sparingly)."""
        _LOGGER.info("Forcing state to %s", state)
        self._previous_state = self._current_state
        self._current_state = state
        self._state_entered_at = self._get_current_time()

    def on_enter_state(self, state: str, callback: Callable) -> None:
        """Register a callback to be called when entering a specific state."""
        if state not in self._state_entry_callbacks:
            self._state_entry_callbacks[state] = []
        self._state_entry_callbacks[state].append(callback)

    def on_exit_state(self, state: str, callback: Callable) -> None:
        """Register a callback to be called when exiting a specific state."""
        if state not in self._state_exit_callbacks:
            self._state_exit_callbacks[state] = []
        self._state_exit_callbacks[state].append(callback)

    def on_transition(
        self, callback: Callable[[str, str, StateTransitionEvent], None]
    ) -> None:
        """Register a callback to be called on any state transition."""
        self._transition_callbacks.append(callback)

    @property
    def current_state(self) -> str:
        """Get the current state."""
        return self._current_state

    @property
    def previous_state(self) -> str | None:
        """Get the previous state."""
        return self._previous_state

    @property
    def time_in_current_state(self) -> float:
        """Get seconds spent in current state."""
        return (self._get_current_time() - self._state_entered_at).total_seconds()

    def is_in_state(self, *states: str) -> bool:
        """Check if current state is one of the given states."""
        return self._current_state in states

    def can_transition(self, event: StateTransitionEvent) -> bool:
        """Check if a transition is possible for the given event."""
        key = (self._current_state, event)
        return key in self._transitions

    def get_info(self) -> dict[str, Any]:
        """Get state machine diagnostic info."""
        return {
            "current_state": self._current_state,
            "previous_state": self._previous_state,
            "state_entered_at": self._state_entered_at.isoformat(),
            "time_in_state": self.time_in_current_state,
            "available_transitions": [
                event.value
                for event in StateTransitionEvent
                if self.can_transition(event)
            ],
        }
