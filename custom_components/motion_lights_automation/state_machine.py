"""State machine for motion lights automation.

This module provides a Home Assistant-specific state machine implementation
that extends the BaseStateMachine with HA-specific time utilities.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.util import dt as dt_util

from .base_state_machine import (
    BaseStateMachine,
    StateTransition,
    StateTransitionEvent,
    STATE_AUTO,
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_MOTION_AUTO,
    STATE_MOTION_MANUAL,
    STATE_OVERRIDDEN,
)

# Re-export for backward compatibility with existing imports
__all__ = [
    "StateTransitionEvent",
    "StateTransition",
    "MotionLightsStateMachine",
    "STATE_AUTO",
    "STATE_IDLE",
    "STATE_MANUAL",
    "STATE_MANUAL_OFF",
    "STATE_MOTION_AUTO",
    "STATE_MOTION_MANUAL",
    "STATE_OVERRIDDEN",
]


def _ha_get_time() -> datetime:
    """Get current time using Home Assistant utilities."""
    return dt_util.now()


class MotionLightsStateMachine(BaseStateMachine):
    """Home Assistant-specific state machine for motion lights automation.

    This class extends BaseStateMachine with Home Assistant-specific time utilities.
    All transition logic is inherited from the core BaseStateMachine.
    """

    def __init__(self, initial_state: str = STATE_IDLE):
        """Initialize the state machine with HA time utilities."""
        super().__init__(initial_state=initial_state, get_current_time=_ha_get_time)
