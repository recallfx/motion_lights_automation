"""Tests for Motion Lights Automation state machine."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util

from homeassistant.components.motion_lights_automation.const import (
    STATE_AUTO,
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_MOTION_AUTO,
    STATE_MOTION_MANUAL,
    STATE_OVERRIDDEN,
)
from homeassistant.components.motion_lights_automation.state_machine import MotionLightsStateMachine, StateTransitionEvent


class TestMotionLightsStateMachine:
    """Test suite for MotionLightsStateMachine."""

    def test_initial_state(self) -> None:
        """Test state machine initializes to IDLE."""
        sm = MotionLightsStateMachine()
        assert sm.current_state == STATE_IDLE

    def test_custom_initial_state(self) -> None:
        """Test state machine initializes with custom initial state."""
        sm = MotionLightsStateMachine(initial_state=STATE_MANUAL)
        assert sm.current_state == STATE_MANUAL

    def test_previous_state_none_initially(self) -> None:
        """Test previous state is None initially."""
        sm = MotionLightsStateMachine()
        assert sm.previous_state is None

    def test_is_in_state(self) -> None:
        """Test is_in_state checks current state."""
        sm = MotionLightsStateMachine(initial_state=STATE_IDLE)
        
        assert sm.is_in_state(STATE_IDLE)
        assert sm.is_in_state(STATE_IDLE, STATE_MANUAL)
        assert not sm.is_in_state(STATE_MANUAL)

    def test_time_in_current_state(self) -> None:
        """Test time_in_current_state property."""
        sm = MotionLightsStateMachine()
        
        # Should have a small non-negative time
        time_in_state = sm.time_in_current_state
        assert time_in_state >= 0

    def test_get_info(self) -> None:
        """Test get_info returns diagnostic information."""
        sm = MotionLightsStateMachine()
        
        info = sm.get_info()
        assert "current_state" in info
        assert "previous_state" in info
        assert "state_entered_at" in info
        assert "time_in_state" in info
        assert "available_transitions" in info
        assert info["current_state"] == STATE_IDLE
        assert info["previous_state"] is None

    # ========================================================================
    # Transition Tests
    # ========================================================================

    def test_motion_on_from_idle(self) -> None:
        """Test MOTION_ON transition from IDLE to MOTION_AUTO."""
        sm = MotionLightsStateMachine(initial_state=STATE_IDLE)
        
        assert sm.transition(StateTransitionEvent.MOTION_ON)
        assert sm.current_state == STATE_MOTION_AUTO
        assert sm.previous_state == STATE_IDLE

    def test_motion_on_from_auto(self) -> None:
        """Test MOTION_ON transition from AUTO to MOTION_AUTO."""
        sm = MotionLightsStateMachine(initial_state=STATE_AUTO)
        
        assert sm.transition(StateTransitionEvent.MOTION_ON)
        assert sm.current_state == STATE_MOTION_AUTO

    def test_motion_on_from_manual(self) -> None:
        """Test MOTION_ON transition from MANUAL to MOTION_MANUAL."""
        sm = MotionLightsStateMachine(initial_state=STATE_MANUAL)
        
        assert sm.transition(StateTransitionEvent.MOTION_ON)
        assert sm.current_state == STATE_MOTION_MANUAL

    def test_motion_off_from_motion_auto(self) -> None:
        """Test MOTION_OFF transition from MOTION_AUTO to AUTO."""
        sm = MotionLightsStateMachine(initial_state=STATE_MOTION_AUTO)
        
        assert sm.transition(StateTransitionEvent.MOTION_OFF)
        assert sm.current_state == STATE_AUTO

    def test_motion_off_from_motion_manual(self) -> None:
        """Test MOTION_OFF transition from MOTION_MANUAL to MANUAL."""
        sm = MotionLightsStateMachine(initial_state=STATE_MOTION_MANUAL)
        
        assert sm.transition(StateTransitionEvent.MOTION_OFF)
        assert sm.current_state == STATE_MANUAL

    def test_override_on_transitions(self) -> None:
        """Test OVERRIDE_ON transitions to OVERRIDDEN from all states."""
        states = [STATE_IDLE, STATE_AUTO, STATE_MANUAL, STATE_MOTION_AUTO, STATE_MOTION_MANUAL]
        
        for state in states:
            sm = MotionLightsStateMachine(initial_state=state)
            assert sm.transition(StateTransitionEvent.OVERRIDE_ON)
            assert sm.current_state == STATE_OVERRIDDEN

    def test_override_off_to_manual(self) -> None:
        """Test OVERRIDE_OFF transition from OVERRIDDEN to MANUAL."""
        sm = MotionLightsStateMachine(initial_state=STATE_OVERRIDDEN)
        
        assert sm.transition(StateTransitionEvent.OVERRIDE_OFF, target_state=STATE_MANUAL)
        assert sm.current_state == STATE_MANUAL

    def test_override_off_to_idle(self) -> None:
        """Test OVERRIDE_OFF transition from OVERRIDDEN to IDLE."""
        sm = MotionLightsStateMachine(initial_state=STATE_OVERRIDDEN)
        
        assert sm.transition(StateTransitionEvent.OVERRIDE_OFF, target_state=STATE_IDLE)
        assert sm.current_state == STATE_IDLE

    def test_manual_intervention_from_motion_auto(self) -> None:
        """Test MANUAL_INTERVENTION from MOTION_AUTO to MOTION_MANUAL."""
        sm = MotionLightsStateMachine(initial_state=STATE_MOTION_AUTO)
        
        assert sm.transition(StateTransitionEvent.MANUAL_INTERVENTION)
        assert sm.current_state == STATE_MOTION_MANUAL

    def test_manual_intervention_from_auto(self) -> None:
        """Test MANUAL_INTERVENTION from AUTO to MANUAL."""
        sm = MotionLightsStateMachine(initial_state=STATE_AUTO)
        
        assert sm.transition(StateTransitionEvent.MANUAL_INTERVENTION)
        assert sm.current_state == STATE_MANUAL

    def test_manual_off_intervention(self) -> None:
        """Test MANUAL_OFF_INTERVENTION from AUTO to MANUAL_OFF."""
        sm = MotionLightsStateMachine(initial_state=STATE_AUTO)
        
        assert sm.transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION)
        assert sm.current_state == STATE_MANUAL_OFF

    def test_manual_off_intervention_from_manual(self) -> None:
        """Test MANUAL_OFF_INTERVENTION from MANUAL to MANUAL_OFF."""
        sm = MotionLightsStateMachine(initial_state=STATE_MANUAL)
        
        assert sm.transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION)
        assert sm.current_state == STATE_MANUAL_OFF

    def test_timer_expired_from_auto(self) -> None:
        """Test TIMER_EXPIRED from AUTO to IDLE."""
        sm = MotionLightsStateMachine(initial_state=STATE_AUTO)
        
        assert sm.transition(StateTransitionEvent.TIMER_EXPIRED)
        assert sm.current_state == STATE_IDLE

    def test_timer_expired_from_manual(self) -> None:
        """Test TIMER_EXPIRED from MANUAL to IDLE."""
        sm = MotionLightsStateMachine(initial_state=STATE_MANUAL)
        
        assert sm.transition(StateTransitionEvent.TIMER_EXPIRED)
        assert sm.current_state == STATE_IDLE

    def test_timer_expired_from_manual_off(self) -> None:
        """Test TIMER_EXPIRED from MANUAL_OFF to IDLE."""
        sm = MotionLightsStateMachine(initial_state=STATE_MANUAL_OFF)
        
        assert sm.transition(StateTransitionEvent.TIMER_EXPIRED)
        assert sm.current_state == STATE_IDLE

    def test_lights_all_off_transitions(self) -> None:
        """Test LIGHTS_ALL_OFF transitions to IDLE."""
        # MANUAL state does NOT transition on LIGHTS_ALL_OFF - it uses MANUAL_OFF_INTERVENTION instead
        states = [STATE_AUTO, STATE_MOTION_AUTO, STATE_MOTION_MANUAL]
        
        for state in states:
            sm = MotionLightsStateMachine(initial_state=state)
            assert sm.transition(StateTransitionEvent.LIGHTS_ALL_OFF)
            assert sm.current_state == STATE_IDLE

    def test_invalid_transition(self) -> None:
        """Test invalid transition returns False."""
        sm = MotionLightsStateMachine(initial_state=STATE_IDLE)
        
        # MOTION_OFF is not valid from IDLE
        assert not sm.transition(StateTransitionEvent.MOTION_OFF)
        assert sm.current_state == STATE_IDLE  # State unchanged

    def test_same_state_transition_prevented(self) -> None:
        """Test transition to same state is prevented."""
        sm = MotionLightsStateMachine(initial_state=STATE_IDLE)
        sm.transition(StateTransitionEvent.MOTION_ON)
        
        # Try to transition MOTION_AUTO -> MOTION_AUTO (not valid)
        assert not sm.transition(StateTransitionEvent.MOTION_ON)

    # ========================================================================
    # Callback Tests
    # ========================================================================

    def test_on_enter_state_callback(self) -> None:
        """Test on_enter_state callback is called."""
        sm = MotionLightsStateMachine()
        
        callback_called = []
        
        def callback():
            callback_called.append(True)
        
        sm.on_enter_state(STATE_MOTION_AUTO, callback)
        sm.transition(StateTransitionEvent.MOTION_ON)
        
        assert callback_called

    def test_on_exit_state_callback(self) -> None:
        """Test on_exit_state callback is called."""
        sm = MotionLightsStateMachine(initial_state=STATE_MOTION_AUTO)
        
        callback_called = []
        
        def callback():
            callback_called.append(True)
        
        sm.on_exit_state(STATE_MOTION_AUTO, callback)
        sm.transition(StateTransitionEvent.MOTION_OFF)
        
        assert callback_called

    def test_on_transition_callback(self) -> None:
        """Test on_transition callback is called with correct parameters."""
        sm = MotionLightsStateMachine()
        
        transitions_recorded = []
        
        def callback(old_state, new_state, event):
            transitions_recorded.append((old_state, new_state, event))
        
        sm.on_transition(callback)
        sm.transition(StateTransitionEvent.MOTION_ON)
        
        assert len(transitions_recorded) == 1
        old_state, new_state, event = transitions_recorded[0]
        assert old_state == STATE_IDLE
        assert new_state == STATE_MOTION_AUTO
        assert event == StateTransitionEvent.MOTION_ON

    def test_multiple_callbacks_on_enter(self) -> None:
        """Test multiple on_enter callbacks are all called."""
        sm = MotionLightsStateMachine()
        
        calls = []
        
        def callback1():
            calls.append("callback1")
        
        def callback2():
            calls.append("callback2")
        
        sm.on_enter_state(STATE_MOTION_AUTO, callback1)
        sm.on_enter_state(STATE_MOTION_AUTO, callback2)
        sm.transition(StateTransitionEvent.MOTION_ON)
        
        assert "callback1" in calls
        assert "callback2" in calls

    def test_callback_with_exception_handled(self) -> None:
        """Test exceptions in callbacks are handled gracefully."""
        sm = MotionLightsStateMachine()
        
        callback_called = []
        
        def bad_callback():
            raise RuntimeError("Test error")
        
        def good_callback():
            callback_called.append(True)
        
        sm.on_enter_state(STATE_MOTION_AUTO, bad_callback)
        sm.on_enter_state(STATE_MOTION_AUTO, good_callback)
        
        # Should not raise, despite bad_callback raising
        sm.transition(StateTransitionEvent.MOTION_ON)
        
        # good_callback should still be called
        assert callback_called

    # ========================================================================
    # Force State Tests
    # ========================================================================

    def test_force_state(self) -> None:
        """Test force_state method bypasses transitions."""
        sm = MotionLightsStateMachine(initial_state=STATE_IDLE)
        
        # Force to a state that's not reachable via normal transitions
        sm.force_state(STATE_MANUAL)
        
        assert sm.current_state == STATE_MANUAL

    def test_force_state_updates_previous(self) -> None:
        """Test force_state updates previous state."""
        sm = MotionLightsStateMachine(initial_state=STATE_IDLE)
        sm.force_state(STATE_MANUAL)
        
        assert sm.previous_state == STATE_IDLE

    # ========================================================================
    # Can Transition Tests
    # ========================================================================

    def test_can_transition(self) -> None:
        """Test can_transition returns correct values."""
        sm = MotionLightsStateMachine(initial_state=STATE_IDLE)
        
        # MOTION_ON is valid from IDLE
        assert sm.can_transition(StateTransitionEvent.MOTION_ON)
        
        # MOTION_OFF is not valid from IDLE
        assert not sm.can_transition(StateTransitionEvent.MOTION_OFF)

    def test_available_transitions_in_info(self) -> None:
        """Test available_transitions are listed in get_info."""
        sm = MotionLightsStateMachine(initial_state=STATE_IDLE)
        
        info = sm.get_info()
        available = info["available_transitions"]
        
        # MOTION_ON and OVERRIDE_ON should be available from IDLE
        assert StateTransitionEvent.MOTION_ON.value in available
        assert StateTransitionEvent.OVERRIDE_ON.value in available

    # ========================================================================
    # Complex Scenario Tests
    # ========================================================================

    def test_full_automation_cycle(self) -> None:
        """Test complete automation cycle: IDLE -> MOTION -> AUTO -> IDLE."""
        sm = MotionLightsStateMachine()
        
        # Motion detected
        assert sm.transition(StateTransitionEvent.MOTION_ON)
        assert sm.current_state == STATE_MOTION_AUTO
        
        # Motion ends
        assert sm.transition(StateTransitionEvent.MOTION_OFF)
        assert sm.current_state == STATE_AUTO
        
        # Timer expires
        assert sm.transition(StateTransitionEvent.TIMER_EXPIRED)
        assert sm.current_state == STATE_IDLE

    def test_manual_intervention_cycle(self) -> None:
        """Test manual intervention: MOTION_AUTO -> MOTION_MANUAL -> MANUAL."""
        sm = MotionLightsStateMachine(initial_state=STATE_MOTION_AUTO)
        
        # User intervenes
        assert sm.transition(StateTransitionEvent.MANUAL_INTERVENTION)
        assert sm.current_state == STATE_MOTION_MANUAL
        
        # Motion ends
        assert sm.transition(StateTransitionEvent.MOTION_OFF)
        assert sm.current_state == STATE_MANUAL

    def test_override_cycle(self) -> None:
        """Test override functionality."""
        sm = MotionLightsStateMachine(initial_state=STATE_AUTO)
        
        # Override activated
        assert sm.transition(StateTransitionEvent.OVERRIDE_ON)
        assert sm.current_state == STATE_OVERRIDDEN
        
        # Override deactivated, go to MANUAL
        assert sm.transition(StateTransitionEvent.OVERRIDE_OFF, target_state=STATE_MANUAL)
        assert sm.current_state == STATE_MANUAL

    def test_multiple_transitions_track_history(self) -> None:
        """Test multiple transitions maintain correct history."""
        sm = MotionLightsStateMachine()
        
        transitions_list = []
        
        def track(old, new, event):
            transitions_list.append((old, new))
        
        sm.on_transition(track)
        
        # Perform multiple transitions
        sm.transition(StateTransitionEvent.MOTION_ON)
        sm.transition(StateTransitionEvent.MOTION_OFF)
        sm.transition(StateTransitionEvent.TIMER_EXPIRED)
        
        assert len(transitions_list) == 3
        assert transitions_list[0] == (STATE_IDLE, STATE_MOTION_AUTO)
        assert transitions_list[1] == (STATE_MOTION_AUTO, STATE_AUTO)
        assert transitions_list[2] == (STATE_AUTO, STATE_IDLE)

    def test_state_entered_at_updates(self) -> None:
        """Test state_entered_at timestamp updates on transitions."""
        sm = MotionLightsStateMachine()
        
        initial_time = sm.get_info()["state_entered_at"]
        
        # Small delay
        import time
        time.sleep(0.01)
        
        sm.transition(StateTransitionEvent.MOTION_ON)
        new_time = sm.get_info()["state_entered_at"]
        
        assert initial_time != new_time
