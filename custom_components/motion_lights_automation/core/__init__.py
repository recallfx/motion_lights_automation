"""Core logic for motion lights automation.

This module contains the shared logic that can be used by both
the Home Assistant integration and the standalone simulation.
"""

from .state_machine import (
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
from .timer_manager import BaseTimerManager, TimerType, BaseTimer

__all__ = [
    "BaseStateMachine",
    "StateTransition",
    "StateTransitionEvent",
    "STATE_AUTO",
    "STATE_IDLE",
    "STATE_MANUAL",
    "STATE_MANUAL_OFF",
    "STATE_MOTION_AUTO",
    "STATE_MOTION_MANUAL",
    "STATE_OVERRIDDEN",
    "BaseTimerManager",
    "TimerType",
    "BaseTimer",
]
