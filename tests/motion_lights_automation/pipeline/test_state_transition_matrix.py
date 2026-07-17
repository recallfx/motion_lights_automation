"""Exhaustive state-transition matrix tests for the state machine.

Tests every (state, event) combination -- both valid transitions and
combinations that must be rejected -- to guarantee the transition table
is complete and correct.
"""

from __future__ import annotations

import time

from custom_components.motion_lights_automation.state_machine import (
    STATE_AUTO,
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_MOTION_AUTO,
    STATE_MOTION_MANUAL,
    STATE_OVERRIDDEN,
    MotionLightsStateMachine,
    StateTransitionEvent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_STATES = [
    STATE_IDLE,
    STATE_MOTION_AUTO,
    STATE_AUTO,
    STATE_MOTION_MANUAL,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_OVERRIDDEN,
]


def _make_sm(state: str) -> MotionLightsStateMachine:
    """Create a state machine forced into *state*."""
    sm = MotionLightsStateMachine()
    sm.force_state(state)
    return sm


# ===================================================================
# 1. MOTION_ON
# ===================================================================


class TestMotionOnTransitions:
    """MOTION_ON event from every state."""

    def test_from_idle(self) -> None:
        sm = _make_sm(STATE_IDLE)
        assert sm.transition(StateTransitionEvent.MOTION_ON) is True
        assert sm.current_state == STATE_MOTION_AUTO

    def test_from_auto(self) -> None:
        sm = _make_sm(STATE_AUTO)
        assert sm.transition(StateTransitionEvent.MOTION_ON) is True
        assert sm.current_state == STATE_MOTION_AUTO

    def test_from_manual(self) -> None:
        sm = _make_sm(STATE_MANUAL)
        assert sm.transition(StateTransitionEvent.MOTION_ON) is True
        assert sm.current_state == STATE_MOTION_MANUAL

    def test_from_manual_off_is_ignored(self) -> None:
        """MANUAL_OFF -> MANUAL_OFF is a same-state transition (returns False)."""
        sm = _make_sm(STATE_MANUAL_OFF)
        assert sm.transition(StateTransitionEvent.MOTION_ON) is False
        assert sm.current_state == STATE_MANUAL_OFF

    def test_from_motion_auto_no_transition(self) -> None:
        sm = _make_sm(STATE_MOTION_AUTO)
        assert sm.transition(StateTransitionEvent.MOTION_ON) is False
        assert sm.current_state == STATE_MOTION_AUTO

    def test_from_motion_manual_no_transition(self) -> None:
        sm = _make_sm(STATE_MOTION_MANUAL)
        assert sm.transition(StateTransitionEvent.MOTION_ON) is False
        assert sm.current_state == STATE_MOTION_MANUAL

    def test_from_overridden_no_transition(self) -> None:
        sm = _make_sm(STATE_OVERRIDDEN)
        assert sm.transition(StateTransitionEvent.MOTION_ON) is False
        assert sm.current_state == STATE_OVERRIDDEN


# ===================================================================
# 2. MOTION_OFF
# ===================================================================


class TestMotionOffTransitions:
    """MOTION_OFF event from every state."""

    def test_from_motion_auto(self) -> None:
        sm = _make_sm(STATE_MOTION_AUTO)
        assert sm.transition(StateTransitionEvent.MOTION_OFF) is True
        assert sm.current_state == STATE_AUTO

    def test_from_motion_manual(self) -> None:
        sm = _make_sm(STATE_MOTION_MANUAL)
        assert sm.transition(StateTransitionEvent.MOTION_OFF) is True
        assert sm.current_state == STATE_MANUAL

    def test_from_idle_no_transition(self) -> None:
        sm = _make_sm(STATE_IDLE)
        assert sm.transition(StateTransitionEvent.MOTION_OFF) is False
        assert sm.current_state == STATE_IDLE

    def test_from_auto_no_transition(self) -> None:
        sm = _make_sm(STATE_AUTO)
        assert sm.transition(StateTransitionEvent.MOTION_OFF) is False
        assert sm.current_state == STATE_AUTO

    def test_from_manual_no_transition(self) -> None:
        sm = _make_sm(STATE_MANUAL)
        assert sm.transition(StateTransitionEvent.MOTION_OFF) is False
        assert sm.current_state == STATE_MANUAL

    def test_from_manual_off_no_transition(self) -> None:
        sm = _make_sm(STATE_MANUAL_OFF)
        assert sm.transition(StateTransitionEvent.MOTION_OFF) is False
        assert sm.current_state == STATE_MANUAL_OFF

    def test_from_overridden_no_transition(self) -> None:
        sm = _make_sm(STATE_OVERRIDDEN)
        assert sm.transition(StateTransitionEvent.MOTION_OFF) is False
        assert sm.current_state == STATE_OVERRIDDEN


# ===================================================================
# 3. OVERRIDE_ON
# ===================================================================


class TestOverrideOnTransitions:
    """OVERRIDE_ON event from every state."""

    def test_from_idle(self) -> None:
        sm = _make_sm(STATE_IDLE)
        assert sm.transition(StateTransitionEvent.OVERRIDE_ON) is True
        assert sm.current_state == STATE_OVERRIDDEN

    def test_from_auto(self) -> None:
        sm = _make_sm(STATE_AUTO)
        assert sm.transition(StateTransitionEvent.OVERRIDE_ON) is True
        assert sm.current_state == STATE_OVERRIDDEN

    def test_from_manual(self) -> None:
        sm = _make_sm(STATE_MANUAL)
        assert sm.transition(StateTransitionEvent.OVERRIDE_ON) is True
        assert sm.current_state == STATE_OVERRIDDEN

    def test_from_motion_auto(self) -> None:
        sm = _make_sm(STATE_MOTION_AUTO)
        assert sm.transition(StateTransitionEvent.OVERRIDE_ON) is True
        assert sm.current_state == STATE_OVERRIDDEN

    def test_from_motion_manual(self) -> None:
        sm = _make_sm(STATE_MOTION_MANUAL)
        assert sm.transition(StateTransitionEvent.OVERRIDE_ON) is True
        assert sm.current_state == STATE_OVERRIDDEN

    def test_from_manual_off(self) -> None:
        sm = _make_sm(STATE_MANUAL_OFF)
        assert sm.transition(StateTransitionEvent.OVERRIDE_ON) is True
        assert sm.current_state == STATE_OVERRIDDEN

    def test_from_overridden_is_ignored(self) -> None:
        """Same-state transition OVERRIDDEN -> OVERRIDDEN returns False."""
        sm = _make_sm(STATE_OVERRIDDEN)
        assert sm.transition(StateTransitionEvent.OVERRIDE_ON) is False
        assert sm.current_state == STATE_OVERRIDDEN


# ===================================================================
# 4. OVERRIDE_OFF
# ===================================================================


class TestOverrideOffTransitions:
    """OVERRIDE_OFF event from every state."""

    def test_to_manual_with_target_state(self) -> None:
        sm = _make_sm(STATE_OVERRIDDEN)
        assert (
            sm.transition(StateTransitionEvent.OVERRIDE_OFF, target_state=STATE_MANUAL)
            is True
        )
        assert sm.current_state == STATE_MANUAL

    def test_to_idle_with_target_state(self) -> None:
        sm = _make_sm(STATE_OVERRIDDEN)
        assert (
            sm.transition(StateTransitionEvent.OVERRIDE_OFF, target_state=STATE_IDLE)
            is True
        )
        assert sm.current_state == STATE_IDLE

    def test_from_non_overridden_no_transition(self) -> None:
        """OVERRIDE_OFF is only valid from the OVERRIDDEN state."""
        for state in ALL_STATES:
            if state == STATE_OVERRIDDEN:
                continue
            sm = _make_sm(state)
            assert sm.transition(StateTransitionEvent.OVERRIDE_OFF) is False, (
                f"OVERRIDE_OFF should not transition from {state}"
            )
            assert sm.current_state == state


# ===================================================================
# 5. MANUAL_INTERVENTION
# ===================================================================


class TestManualInterventionTransitions:
    """MANUAL_INTERVENTION event from every state."""

    def test_from_motion_auto(self) -> None:
        sm = _make_sm(STATE_MOTION_AUTO)
        assert sm.transition(StateTransitionEvent.MANUAL_INTERVENTION) is True
        assert sm.current_state == STATE_MOTION_MANUAL

    def test_from_auto(self) -> None:
        sm = _make_sm(STATE_AUTO)
        assert sm.transition(StateTransitionEvent.MANUAL_INTERVENTION) is True
        assert sm.current_state == STATE_MANUAL

    def test_from_idle(self) -> None:
        sm = _make_sm(STATE_IDLE)
        assert sm.transition(StateTransitionEvent.MANUAL_INTERVENTION) is True
        assert sm.current_state == STATE_MANUAL

    def test_from_manual_off(self) -> None:
        sm = _make_sm(STATE_MANUAL_OFF)
        assert sm.transition(StateTransitionEvent.MANUAL_INTERVENTION) is True
        assert sm.current_state == STATE_MANUAL

    def test_from_manual_no_transition(self) -> None:
        sm = _make_sm(STATE_MANUAL)
        assert sm.transition(StateTransitionEvent.MANUAL_INTERVENTION) is False
        assert sm.current_state == STATE_MANUAL

    def test_from_motion_manual_no_transition(self) -> None:
        sm = _make_sm(STATE_MOTION_MANUAL)
        assert sm.transition(StateTransitionEvent.MANUAL_INTERVENTION) is False
        assert sm.current_state == STATE_MOTION_MANUAL

    def test_from_overridden_no_transition(self) -> None:
        sm = _make_sm(STATE_OVERRIDDEN)
        assert sm.transition(StateTransitionEvent.MANUAL_INTERVENTION) is False
        assert sm.current_state == STATE_OVERRIDDEN


# ===================================================================
# 6. MANUAL_OFF_INTERVENTION
# ===================================================================


class TestManualOffInterventionTransitions:
    """MANUAL_OFF_INTERVENTION event from every state."""

    def test_from_auto(self) -> None:
        sm = _make_sm(STATE_AUTO)
        assert sm.transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION) is True
        assert sm.current_state == STATE_MANUAL_OFF

    def test_from_manual(self) -> None:
        sm = _make_sm(STATE_MANUAL)
        assert sm.transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION) is True
        assert sm.current_state == STATE_MANUAL_OFF

    def test_from_motion_auto(self) -> None:
        sm = _make_sm(STATE_MOTION_AUTO)
        assert sm.transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION) is True
        assert sm.current_state == STATE_MANUAL_OFF

    def test_from_motion_manual(self) -> None:
        sm = _make_sm(STATE_MOTION_MANUAL)
        assert sm.transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION) is True
        assert sm.current_state == STATE_MANUAL_OFF

    def test_from_idle_no_transition(self) -> None:
        sm = _make_sm(STATE_IDLE)
        assert sm.transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION) is False
        assert sm.current_state == STATE_IDLE

    def test_from_manual_off_no_transition(self) -> None:
        sm = _make_sm(STATE_MANUAL_OFF)
        assert sm.transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION) is False
        assert sm.current_state == STATE_MANUAL_OFF

    def test_from_overridden_no_transition(self) -> None:
        sm = _make_sm(STATE_OVERRIDDEN)
        assert sm.transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION) is False
        assert sm.current_state == STATE_OVERRIDDEN


# ===================================================================
# 7. TIMER_EXPIRED
# ===================================================================


class TestTimerExpiredTransitions:
    """TIMER_EXPIRED event from every state."""

    def test_from_auto(self) -> None:
        sm = _make_sm(STATE_AUTO)
        assert sm.transition(StateTransitionEvent.TIMER_EXPIRED) is True
        assert sm.current_state == STATE_IDLE

    def test_from_manual(self) -> None:
        sm = _make_sm(STATE_MANUAL)
        assert sm.transition(StateTransitionEvent.TIMER_EXPIRED) is True
        assert sm.current_state == STATE_IDLE

    def test_from_manual_off(self) -> None:
        sm = _make_sm(STATE_MANUAL_OFF)
        assert sm.transition(StateTransitionEvent.TIMER_EXPIRED) is True
        assert sm.current_state == STATE_IDLE

    def test_from_idle_no_transition(self) -> None:
        sm = _make_sm(STATE_IDLE)
        assert sm.transition(StateTransitionEvent.TIMER_EXPIRED) is False
        assert sm.current_state == STATE_IDLE

    def test_from_motion_auto_no_transition(self) -> None:
        sm = _make_sm(STATE_MOTION_AUTO)
        assert sm.transition(StateTransitionEvent.TIMER_EXPIRED) is False
        assert sm.current_state == STATE_MOTION_AUTO

    def test_from_motion_manual_no_transition(self) -> None:
        sm = _make_sm(STATE_MOTION_MANUAL)
        assert sm.transition(StateTransitionEvent.TIMER_EXPIRED) is False
        assert sm.current_state == STATE_MOTION_MANUAL

    def test_from_overridden_no_transition(self) -> None:
        sm = _make_sm(STATE_OVERRIDDEN)
        assert sm.transition(StateTransitionEvent.TIMER_EXPIRED) is False
        assert sm.current_state == STATE_OVERRIDDEN


# ===================================================================
# 8. LIGHTS_ALL_OFF
# ===================================================================


class TestLightsAllOffTransitions:
    """LIGHTS_ALL_OFF event from every state."""

    def test_from_auto(self) -> None:
        sm = _make_sm(STATE_AUTO)
        assert sm.transition(StateTransitionEvent.LIGHTS_ALL_OFF) is True
        assert sm.current_state == STATE_IDLE

    def test_from_manual(self) -> None:
        sm = _make_sm(STATE_MANUAL)
        assert sm.transition(StateTransitionEvent.LIGHTS_ALL_OFF) is True
        assert sm.current_state == STATE_IDLE

    def test_from_motion_auto(self) -> None:
        sm = _make_sm(STATE_MOTION_AUTO)
        assert sm.transition(StateTransitionEvent.LIGHTS_ALL_OFF) is True
        assert sm.current_state == STATE_IDLE

    def test_from_motion_manual(self) -> None:
        sm = _make_sm(STATE_MOTION_MANUAL)
        assert sm.transition(StateTransitionEvent.LIGHTS_ALL_OFF) is True
        assert sm.current_state == STATE_IDLE

    def test_from_idle_no_transition(self) -> None:
        sm = _make_sm(STATE_IDLE)
        assert sm.transition(StateTransitionEvent.LIGHTS_ALL_OFF) is False
        assert sm.current_state == STATE_IDLE

    def test_from_manual_off_no_transition(self) -> None:
        sm = _make_sm(STATE_MANUAL_OFF)
        assert sm.transition(StateTransitionEvent.LIGHTS_ALL_OFF) is False
        assert sm.current_state == STATE_MANUAL_OFF

    def test_from_overridden_no_transition(self) -> None:
        sm = _make_sm(STATE_OVERRIDDEN)
        assert sm.transition(StateTransitionEvent.LIGHTS_ALL_OFF) is False
        assert sm.current_state == STATE_OVERRIDDEN


# ===================================================================
# 9. Callback execution
# ===================================================================


class TestCallbackExecution:
    """Verify that callbacks fire with the correct context."""

    def test_entry_callback_receives_context(self) -> None:
        sm = _make_sm(STATE_IDLE)
        captured: list[tuple] = []

        def cb(from_state, to_state, event):
            captured.append((from_state, to_state, event))

        sm.on_enter_state(STATE_MOTION_AUTO, cb)
        sm.transition(StateTransitionEvent.MOTION_ON)

        assert len(captured) == 1
        assert captured[0] == (
            STATE_IDLE,
            STATE_MOTION_AUTO,
            StateTransitionEvent.MOTION_ON,
        )

    def test_exit_callback_receives_context(self) -> None:
        sm = _make_sm(STATE_IDLE)
        captured: list[tuple] = []

        def cb(from_state, to_state, event):
            captured.append((from_state, to_state, event))

        sm.on_exit_state(STATE_IDLE, cb)
        sm.transition(StateTransitionEvent.MOTION_ON)

        assert len(captured) == 1
        assert captured[0] == (
            STATE_IDLE,
            STATE_MOTION_AUTO,
            StateTransitionEvent.MOTION_ON,
        )

    def test_transition_callback_receives_context(self) -> None:
        sm = _make_sm(STATE_AUTO)
        captured: list[tuple] = []

        def cb(from_state, to_state, event):
            captured.append((from_state, to_state, event))

        sm.on_transition(cb)
        sm.transition(StateTransitionEvent.TIMER_EXPIRED)

        assert len(captured) == 1
        assert captured[0] == (
            STATE_AUTO,
            STATE_IDLE,
            StateTransitionEvent.TIMER_EXPIRED,
        )

    def test_callback_exception_does_not_block_transition(self) -> None:
        sm = _make_sm(STATE_IDLE)

        def bad_cb(from_state, to_state, event):
            raise RuntimeError("boom")

        sm.on_enter_state(STATE_MOTION_AUTO, bad_cb)

        # Transition should still succeed despite the exception.
        assert sm.transition(StateTransitionEvent.MOTION_ON) is True
        assert sm.current_state == STATE_MOTION_AUTO

    def test_no_args_callback_still_works(self) -> None:
        """Backward-compat: zero-arg callbacks are supported via TypeError fallback."""
        sm = _make_sm(STATE_IDLE)
        called = []

        def cb():
            called.append(True)

        sm.on_enter_state(STATE_MOTION_AUTO, cb)
        sm.transition(StateTransitionEvent.MOTION_ON)

        assert called

    def test_multiple_entry_callbacks_all_fire(self) -> None:
        sm = _make_sm(STATE_IDLE)
        calls: list[str] = []

        sm.on_enter_state(STATE_MOTION_AUTO, lambda *_: calls.append("a"))
        sm.on_enter_state(STATE_MOTION_AUTO, lambda *_: calls.append("b"))
        sm.on_enter_state(STATE_MOTION_AUTO, lambda *_: calls.append("c"))

        sm.transition(StateTransitionEvent.MOTION_ON)

        assert calls == ["a", "b", "c"]


# ===================================================================
# 10. Edge cases
# ===================================================================


class TestEdgeCases:
    """Miscellaneous edge-case behaviour."""

    def test_transition_to_same_state_returns_false(self) -> None:
        """Explicit same-state transitions (e.g. OVERRIDE_ON from OVERRIDDEN)."""
        sm = _make_sm(STATE_OVERRIDDEN)
        assert sm.transition(StateTransitionEvent.OVERRIDE_ON) is False
        assert sm.current_state == STATE_OVERRIDDEN

    def test_force_state_updates_correctly(self) -> None:
        sm = MotionLightsStateMachine()
        sm.force_state(STATE_MANUAL_OFF)
        assert sm.current_state == STATE_MANUAL_OFF

    def test_force_state_does_not_fire_callbacks(self) -> None:
        sm = MotionLightsStateMachine()
        fired = []

        sm.on_enter_state(STATE_MANUAL, lambda *_: fired.append(True))
        sm.on_exit_state(STATE_IDLE, lambda *_: fired.append(True))
        sm.on_transition(lambda *_: fired.append(True))

        sm.force_state(STATE_MANUAL)

        assert fired == [], "force_state must not fire any callbacks"

    def test_time_in_current_state_increases(self) -> None:
        sm = MotionLightsStateMachine()
        t0 = sm.time_in_current_state
        time.sleep(0.02)
        t1 = sm.time_in_current_state
        assert t1 > t0

    def test_previous_state_tracks_correctly(self) -> None:
        sm = MotionLightsStateMachine()  # starts IDLE
        sm.transition(StateTransitionEvent.MOTION_ON)  # -> MOTION_AUTO
        assert sm.previous_state == STATE_IDLE

        sm.transition(StateTransitionEvent.MOTION_OFF)  # -> AUTO
        assert sm.previous_state == STATE_MOTION_AUTO

        sm.transition(StateTransitionEvent.TIMER_EXPIRED)  # -> IDLE
        assert sm.previous_state == STATE_AUTO

    def test_get_info_returns_valid_dict(self) -> None:
        sm = _make_sm(STATE_MANUAL)
        info = sm.get_info()

        assert info["current_state"] == STATE_MANUAL
        assert "previous_state" in info
        assert "state_entered_at" in info
        assert isinstance(info["time_in_state"], float)
        assert isinstance(info["available_transitions"], list)
        # MANUAL should support several events
        assert len(info["available_transitions"]) > 0

    def test_can_transition_reflects_table(self) -> None:
        sm = _make_sm(STATE_IDLE)
        # Valid from IDLE
        assert sm.can_transition(StateTransitionEvent.MOTION_ON) is True
        assert sm.can_transition(StateTransitionEvent.OVERRIDE_ON) is True
        assert sm.can_transition(StateTransitionEvent.MANUAL_INTERVENTION) is True
        # Not valid from IDLE
        assert sm.can_transition(StateTransitionEvent.MOTION_OFF) is False
        assert sm.can_transition(StateTransitionEvent.TIMER_EXPIRED) is False
        assert sm.can_transition(StateTransitionEvent.LIGHTS_ALL_OFF) is False

    def test_is_in_state_with_multiple_args(self) -> None:
        sm = _make_sm(STATE_AUTO)
        assert sm.is_in_state(STATE_AUTO) is True
        assert sm.is_in_state(STATE_AUTO, STATE_MANUAL) is True
        assert sm.is_in_state(STATE_IDLE, STATE_OVERRIDDEN) is False
