"""Tests that validate correct behavior AFTER bugs are fixed.

These tests FAIL against the current code and should PASS once fixes are applied.

Each test describes the expected correct behavior for the corresponding bug.
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
    STATE_MOTION_MANUAL,
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
        entry_id="test_fix_entry",
        source="user",
        unique_id="test_fix_unique",
        discovery_keys={},
    )


@pytest.fixture
def ambient_entry() -> ConfigEntry:
    """Create a config entry with a lux ambient light sensor."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Ambient Fix",
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
        entry_id="test_ambient_fix_entry",
        source="user",
        unique_id="test_ambient_fix_unique",
        discovery_keys={},
    )


# =============================================================================
# FIX 1: State entry callbacks should receive from_state
# =============================================================================


class TestFix1_EntryCallbacksReceiveFromState:
    """After the fix, entry callbacks should receive transition context
    so that diagnostic log messages are generated correctly."""

    def test_state_machine_entry_callback_receives_from_state(self) -> None:
        """Entry callbacks should receive the previous state information.

        The state machine should pass from_state/to_state/event to callbacks
        so they can make informed decisions about what to log.
        """
        sm = MotionLightsStateMachine(initial_state=STATE_IDLE)

        received_from_states = []

        # The callback needs to accept being called with from_state info
        # After fix, the state machine should pass transition context
        def capture_callback(*args, **kwargs):
            received_from_states.append({"args": args, "kwargs": kwargs})

        sm.on_enter_state(STATE_MOTION_AUTO, capture_callback)
        sm.transition(StateTransitionEvent.MOTION_ON)

        assert len(received_from_states) == 1
        # AFTER FIX: callback should receive from_state information
        # The exact mechanism may vary (positional args or kwargs)
        # but the callback must have access to the previous state
        call = received_from_states[0]
        has_from_state = (
            len(call["args"]) > 0
            or "from_state" in call["kwargs"]
            or "old_state" in call["kwargs"]
        )
        assert has_from_state, (
            "Entry callback should receive from_state info after fix. "
            f"Got args={call['args']}, kwargs={call['kwargs']}"
        )

    async def test_on_enter_idle_logs_timeout_from_auto(
        self, hass: HomeAssistant, basic_entry: ConfigEntry
    ) -> None:
        """After fix: AUTO -> IDLE should log 'Lights turned off (timeout)'."""
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
                "Expected 'Lights turned off (timeout)' in event log after "
                f"AUTO -> IDLE transition. Got: {coordinator._event_log}"
            )
        finally:
            coordinator.async_cleanup_listeners()

    async def test_on_enter_manual_logs_lights_turned_on_manually(
        self, hass: HomeAssistant, basic_entry: ConfigEntry
    ) -> None:
        """After fix: IDLE -> MANUAL should log 'Lights turned on manually'."""
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
                "Expected 'Lights turned on manually' in event log after "
                f"IDLE -> MANUAL transition. Got: {coordinator._event_log}"
            )
        finally:
            coordinator.async_cleanup_listeners()

    async def test_on_enter_idle_logs_ready_from_manual_off(
        self, hass: HomeAssistant, basic_entry: ConfigEntry
    ) -> None:
        """After fix: MANUAL_OFF -> IDLE should log 'Ready - waiting for motion'."""
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
                "Expected 'Ready - waiting for motion' in event log after "
                f"MANUAL_OFF -> IDLE transition. Got: {coordinator._event_log}"
            )
        finally:
            coordinator.async_cleanup_listeners()

    async def test_on_enter_manual_logs_motion_cleared_from_motion_manual(
        self, hass: HomeAssistant, basic_entry: ConfigEntry
    ) -> None:
        """After fix: MOTION_MANUAL -> MANUAL should log 'Motion cleared - starting timeout'."""
        hass.states.async_set("binary_sensor.motion", "on")
        hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})

        coordinator = MotionLightsCoordinator(hass, basic_entry)
        await coordinator.async_setup_listeners()

        try:
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)
            coordinator.state_machine.force_state(STATE_MOTION_MANUAL)
            coordinator.light_controller.refresh_all_states()
            coordinator._event_log.clear()

            # Motion stops
            hass.states.async_set("binary_sensor.motion", "off")
            await hass.async_block_till_done()

            assert coordinator.current_state == STATE_MANUAL

            motion_cleared_messages = [
                msg for msg in coordinator._event_log if "motion cleared" in msg.lower()
            ]
            assert len(motion_cleared_messages) > 0, (
                "Expected 'Motion cleared - starting timeout' in event log after "
                f"MOTION_MANUAL -> MANUAL transition. Got: {coordinator._event_log}"
            )
        finally:
            coordinator.async_cleanup_listeners()


# =============================================================================
# FIX 2: Ambient light handler should handle MOTION_AUTO
# =============================================================================


class TestFix2_AmbientLightHandlesMotionAuto:
    """After the fix, the ambient light handler should turn on lights
    when it gets dark while in MOTION_AUTO state."""

    async def test_lights_turn_on_when_dark_in_motion_auto(
        self, hass: HomeAssistant, ambient_entry: ConfigEntry
    ) -> None:
        """After fix: becoming dark in MOTION_AUTO should call _async_turn_on_lights.

        Steps:
        1. Bright room, motion active → MOTION_AUTO, lights off (brightness=0)
        2. Lux drops below threshold → ambient handler fires
        3. FIXED: Handler processes MOTION_AUTO → calls _async_turn_on_lights
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

            # Motion detected while bright → MOTION_AUTO, lights stay off
            coordinator.state_machine.force_state(STATE_MOTION_AUTO)
            coordinator.light_controller.refresh_all_states()

            assert not coordinator.light_controller.any_lights_on()

            # Spy on _async_turn_on_lights to verify it gets called
            turn_on_called = False
            original_turn_on = coordinator._async_turn_on_lights

            async def spy_turn_on():
                nonlocal turn_on_called
                turn_on_called = True
                await original_turn_on()

            coordinator._async_turn_on_lights = spy_turn_on

            # Now it gets dark
            hass.states.async_set(
                "sensor.lux",
                "10",
                attributes={"unit_of_measurement": "lx"},
            )
            await hass.async_block_till_done()

            # AFTER FIX: _async_turn_on_lights should have been called
            assert turn_on_called, (
                "Expected _async_turn_on_lights to be called when ambient light "
                "changes from bright to dark while in MOTION_AUTO state. "
                "The ambient handler must handle MOTION_AUTO."
            )
        finally:
            coordinator.async_cleanup_listeners()


# =============================================================================
# FIX 3: Timestamps should use dt_util.now()
# =============================================================================


class TestFix3_TimezoneAwareDiagnostics:
    """After the fix, diagnostic timestamps should be timezone-aware."""

    async def test_log_event_uses_timezone_aware_datetime(
        self, hass: HomeAssistant, basic_entry: ConfigEntry
    ) -> None:
        """After fix: _log_event should use dt_util.now() for timezone-aware timestamps."""
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
                f"Got naive timestamp: {timestamp_str}"
            )
        finally:
            coordinator.async_cleanup_listeners()

    async def test_log_transition_uses_timezone_aware_datetime(
        self, hass: HomeAssistant, basic_entry: ConfigEntry
    ) -> None:
        """After fix: _log_transition should store timezone-aware datetime."""
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
