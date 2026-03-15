"""Validation tests that prove specific bugs exist in the codebase.

Each test in this file is designed to FAIL against the current code,
demonstrating a real bug. Once the bugs are fixed, these tests should pass.

Bugs validated:
1. State entry callbacks don't receive from_state → diagnostic log messages missing
2. Ambient light handler misses MOTION_AUTO → lights stay off when it gets dark
3. datetime.now() used instead of dt_util.now() → inconsistent timestamps
4. Redundant condition in _handle_manual_intervention
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_EXTENDED_TIMEOUT,
    CONF_LIGHTS,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    DOMAIN,
)
from custom_components.motion_lights_automation.state_machine import (
    STATE_AUTO,
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_MOTION_AUTO,
    MotionLightsStateMachine,
    StateTransitionEvent,
)
from custom_components.motion_lights_automation.motion_coordinator import (
    MotionLightsCoordinator,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def basic_entry() -> ConfigEntry:
    """Create a basic config entry for testing."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Motion Lights",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.ceiling"],
            CONF_MOTION_ACTIVATION: True,
            CONF_NO_MOTION_WAIT: 300,
            CONF_EXTENDED_TIMEOUT: 1200,
            CONF_BRIGHTNESS_ACTIVE: 80,
            CONF_BRIGHTNESS_INACTIVE: 10,
        },
        options={},
        entry_id="test_bug_entry",
        source="user",
        unique_id="test_bug_unique",
        discovery_keys={},
    )


@pytest.fixture
def ambient_entry() -> ConfigEntry:
    """Create a config entry with a lux ambient light sensor."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Ambient Bug",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.ceiling"],
            CONF_MOTION_ACTIVATION: True,
            CONF_NO_MOTION_WAIT: 300,
            CONF_EXTENDED_TIMEOUT: 1200,
            CONF_BRIGHTNESS_ACTIVE: 80,
            CONF_BRIGHTNESS_INACTIVE: 10,
            CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
            CONF_AMBIENT_LIGHT_THRESHOLD: 50,
        },
        options={},
        entry_id="test_ambient_bug_entry",
        source="user",
        unique_id="test_ambient_bug_unique",
        discovery_keys={},
    )


# =============================================================================
# BUG 1: State entry callbacks never receive from_state
# =============================================================================


class TestBug1_EntryCallbacksNoFromState:
    """Prove that state entry callbacks don't receive from_state.

    The state machine calls `callback()` with no arguments, but the
    coordinator's _on_enter_manual and _on_enter_idle use from_state
    to decide which human event log message to emit.

    Result: Messages like "Lights turned on manually" and
    "Lights turned off (timeout)" never appear in the event log.
    """

    def test_state_machine_entry_callback_receives_args(self) -> None:
        """Verify entry callbacks receive from_state, to_state, event args.

        After fix: the state machine passes (old_state, new_state, event) to callbacks.
        """
        sm = MotionLightsStateMachine(initial_state=STATE_IDLE)

        received_args = []

        def capture_callback(*args, **kwargs):
            received_args.append({"args": args, "kwargs": kwargs})

        sm.on_enter_state(STATE_MOTION_AUTO, capture_callback)
        sm.transition(StateTransitionEvent.MOTION_ON)

        assert len(received_args) == 1
        # FIXED: callback receives (from_state, to_state, event)
        assert len(received_args[0]["args"]) == 3
        assert received_args[0]["args"][0] == STATE_IDLE  # from_state
        assert received_args[0]["args"][1] == STATE_MOTION_AUTO  # to_state

    async def test_on_enter_idle_log_message_from_auto_timeout(
        self, hass: HomeAssistant, basic_entry: ConfigEntry
    ) -> None:
        """Verify AUTO -> IDLE via TIMER_EXPIRED logs 'Lights turned off (timeout)'."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.ceiling", "off")

        coordinator = MotionLightsCoordinator(hass, basic_entry)
        await coordinator.async_setup_listeners()

        try:
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)
            coordinator.state_machine.force_state(STATE_AUTO)
            coordinator._event_log.clear()

            await coordinator._async_timer_expired("motion")

            assert coordinator.current_state == STATE_IDLE

            timeout_messages = [
                msg for msg in coordinator._event_log if "timeout" in msg.lower()
            ]
            assert len(timeout_messages) > 0, (
                "Expected 'Lights turned off (timeout)' in event log. "
                f"Got: {coordinator._event_log}"
            )
        finally:
            coordinator.async_cleanup_listeners()

    async def test_on_enter_manual_log_message_from_idle(
        self, hass: HomeAssistant, basic_entry: ConfigEntry
    ) -> None:
        """Verify IDLE -> MANUAL logs 'Lights turned on manually'."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.ceiling", "off")

        coordinator = MotionLightsCoordinator(hass, basic_entry)
        await coordinator.async_setup_listeners()

        try:
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)
            coordinator.state_machine.force_state(STATE_IDLE)
            coordinator._event_log.clear()

            with patch.object(
                coordinator.light_controller,
                "is_integration_context",
                return_value=False,
            ):
                hass.states.async_set(
                    "light.ceiling", "on", attributes={"brightness": 200}
                )
                await hass.async_block_till_done()

            assert coordinator.current_state == STATE_MANUAL

            manual_messages = [
                msg
                for msg in coordinator._event_log
                if "turned on manually" in msg.lower()
            ]
            assert len(manual_messages) > 0, (
                "Expected 'Lights turned on manually' in event log. "
                f"Got: {coordinator._event_log}"
            )
        finally:
            coordinator.async_cleanup_listeners()

    async def test_on_enter_idle_log_message_from_manual_off(
        self, hass: HomeAssistant, basic_entry: ConfigEntry
    ) -> None:
        """Verify MANUAL_OFF -> IDLE logs 'Ready - waiting for motion'."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.ceiling", "off")

        coordinator = MotionLightsCoordinator(hass, basic_entry)
        await coordinator.async_setup_listeners()

        try:
            coordinator.state_machine.force_state(STATE_MANUAL_OFF)
            coordinator._event_log.clear()

            await coordinator._async_timer_expired("extended")

            assert coordinator.current_state == STATE_IDLE

            ready_messages = [
                msg for msg in coordinator._event_log if "ready" in msg.lower()
            ]
            assert len(ready_messages) > 0, (
                "Expected 'Ready - waiting for motion' in event log. "
                f"Got: {coordinator._event_log}"
            )
        finally:
            coordinator.async_cleanup_listeners()


# =============================================================================
# BUG 2: Ambient light handler misses MOTION_AUTO state
# =============================================================================


class TestBug2_AmbientLightMissesMotionAuto:
    """Prove that when it gets dark while in MOTION_AUTO, lights don't turn on.

    Scenario: Room is bright → motion detected → MOTION_AUTO → lights stay off
    (brightness=0). Then ambient light decreases → handler fires → MOTION_AUTO
    is NOT in the handled states → lights remain off despite it being dark
    with active motion.
    """

    async def test_lights_turn_on_when_dark_in_motion_auto(
        self, hass: HomeAssistant, ambient_entry: ConfigEntry
    ) -> None:
        """Verify ambient handler calls _async_turn_on_lights in MOTION_AUTO.

        Scenario: bright room → motion → MOTION_AUTO (lights off) → gets dark →
        ambient handler should call _async_turn_on_lights.
        """
        hass.states.async_set("binary_sensor.motion", "on")
        hass.states.async_set("light.ceiling", "off")
        hass.states.async_set(
            "sensor.lux",
            "100",
            attributes={"unit_of_measurement": "lx"},
        )

        coordinator = MotionLightsCoordinator(hass, ambient_entry)
        await coordinator.async_setup_listeners()

        try:
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)
            coordinator.state_machine.force_state(STATE_MOTION_AUTO)
            coordinator.light_controller.refresh_all_states()

            assert not coordinator.light_controller.any_lights_on()

            # Spy on _async_turn_on_lights
            turn_on_called = False
            original_turn_on = coordinator._async_turn_on_lights

            async def spy_turn_on():
                nonlocal turn_on_called
                turn_on_called = True
                await original_turn_on()

            coordinator._async_turn_on_lights = spy_turn_on

            # Lux drops to dark
            hass.states.async_set(
                "sensor.lux",
                "10",
                attributes={"unit_of_measurement": "lx"},
            )
            await hass.async_block_till_done()

            assert turn_on_called, (
                "Expected _async_turn_on_lights to be called when ambient "
                "changes to dark in MOTION_AUTO state."
            )
        finally:
            coordinator.async_cleanup_listeners()

    async def test_ambient_handler_includes_motion_auto(
        self, hass: HomeAssistant, ambient_entry: ConfigEntry
    ) -> None:
        """Verify the ambient handler source includes MOTION_AUTO."""
        hass.states.async_set("binary_sensor.motion", "on")
        hass.states.async_set("light.ceiling", "on", attributes={"brightness": 20})
        hass.states.async_set(
            "sensor.lux",
            "100",
            attributes={"unit_of_measurement": "lx"},
        )

        coordinator = MotionLightsCoordinator(hass, ambient_entry)
        await coordinator.async_setup_listeners()

        try:
            import inspect

            source = inspect.getsource(coordinator._async_ambient_light_changed)

            # MOTION_AUTO should now be in the handler's state checks
            assert "STATE_MOTION_AUTO" in source, (
                "STATE_MOTION_AUTO should be in the ambient handler"
            )
        finally:
            coordinator.async_cleanup_listeners()


# =============================================================================
# BUG 3: datetime.now() instead of dt_util.now() in diagnostics
# =============================================================================


class TestBug3_NaiveDatetimeInDiagnostics:
    """Prove that diagnostic logging uses naive datetime instead of timezone-aware.

    The coordinator uses datetime.now() in _log_event, _log_human_event,
    and _log_transition, while the rest of the codebase uses dt_util.now().
    """

    async def test_log_event_uses_timezone_aware_datetime(
        self, hass: HomeAssistant, basic_entry: ConfigEntry
    ) -> None:
        """Verify _log_event timestamps are timezone-aware."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.ceiling", "off")

        coordinator = MotionLightsCoordinator(hass, basic_entry)
        await coordinator.async_setup_listeners()

        try:
            coordinator._events.clear()
            coordinator._log_event("test_event", {"detail": "test"})

            assert len(coordinator._events) == 1
            timestamp_str = coordinator._events[0]["timestamp"]

            from datetime import datetime

            ts = datetime.fromisoformat(timestamp_str)

            assert ts.tzinfo is not None, (
                "Expected timezone-aware timestamp from _log_event. "
                f"Got naive: {timestamp_str}"
            )
        finally:
            coordinator.async_cleanup_listeners()

    async def test_log_transition_uses_timezone_aware_datetime(
        self, hass: HomeAssistant, basic_entry: ConfigEntry
    ) -> None:
        """Verify _log_transition stores timezone-aware datetime."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.ceiling", "off")

        coordinator = MotionLightsCoordinator(hass, basic_entry)
        await coordinator.async_setup_listeners()

        try:
            coordinator._log_transition("idle", "auto", "test")

            assert coordinator._last_transition_time is not None
            assert coordinator._last_transition_time.tzinfo is not None, (
                "Expected timezone-aware datetime from _log_transition. "
                f"Got: {coordinator._last_transition_time}"
            )
        finally:
            coordinator.async_cleanup_listeners()


# =============================================================================
# BUG 4: Redundant condition in _handle_manual_intervention
# =============================================================================


class TestBug4_RedundantCondition:
    """Prove the redundant boolean condition in _handle_manual_intervention.

    Line 686-688:
        if new_state.state == "on" or (
            new_state.state == "on" and old_state.state == "on"
        ):

    The second condition is a subset of the first. This is logically
    equivalent to just: if new_state.state == "on":
    """

    def test_simplified_condition_in_source(self) -> None:
        """Verify the condition is simplified (no redundant sub-condition)."""
        import inspect
        from custom_components.motion_lights_automation.motion_coordinator import (
            MotionLightsCoordinator,
        )

        source = inspect.getsource(MotionLightsCoordinator._handle_manual_intervention)

        # The old redundant pattern should no longer exist
        assert 'new_state.state == "on" or (' not in source, (
            "Redundant condition pattern should be simplified"
        )

    def test_conditions_are_logically_equivalent(self) -> None:
        """Prove the two conditions are equivalent for all input combinations."""
        for new_state_val in ["on", "off", "unavailable"]:
            for old_state_val in ["on", "off", "unavailable"]:
                # Original condition
                original = new_state_val == "on" or (
                    new_state_val == "on" and old_state_val == "on"
                )
                # Simplified condition
                simplified = new_state_val == "on"

                assert original == simplified, (
                    f"Conditions differ for new={new_state_val}, old={old_state_val}: "
                    f"original={original}, simplified={simplified}"
                )
