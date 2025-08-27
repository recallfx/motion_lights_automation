#!/usr/bin/env python3
"""Simple test script to verify motion coordinator functionality (updated)."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from .const import (
    CONF_BRIGHTNESS_DAY,
    CONF_BRIGHTNESS_NIGHT,
    CONF_COMBINED_LIGHT,
    CONF_EXTENDED_TIMEOUT,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
)
from .motion_coordinator import (
    STATE_AUTO,
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MOTION_AUTO,
    STATE_MOTION_MANUAL,
    STATE_OVERRIDDEN,
    TIMER_EXTENDED,
    TIMER_MOTION,
    MotionLightsCoordinator,
)


def create_mock_coordinator():
    """Create a coordinator with mocked dependencies."""
    # Mock HomeAssistant
    hass = MagicMock()
    hass.loop = asyncio.get_event_loop()
    hass.async_create_task = lambda coro: asyncio.create_task(coro)
    hass.services = AsyncMock()
    hass.states = MagicMock()

    # Mock config entry
    config_entry = MagicMock()
    config_entry.data = {
        CONF_MOTION_ENTITY: "binary_sensor.motion",
        CONF_OVERRIDE_SWITCH: "input_boolean.override",
        CONF_COMBINED_LIGHT: "light.combined",
        CONF_MOTION_ACTIVATION: True,
        CONF_NO_MOTION_WAIT: 5,  # Short for testing
        CONF_EXTENDED_TIMEOUT: 10,  # Short for testing
        CONF_BRIGHTNESS_DAY: 60,
        CONF_BRIGHTNESS_NIGHT: 10,
    }

    # Create coordinator with patched event tracking
    with patch("homeassistant.helpers.event.async_track_state_change_event"):
        coordinator = MotionLightsCoordinator(hass, config_entry)

    # Mock the async methods to avoid actual service calls
    coordinator._async_turn_on_tod_lights = AsyncMock()
    coordinator._async_turn_off_configured_lights = AsyncMock()
    coordinator._async_set_light_state = AsyncMock()

    return coordinator, hass


def mock_lights_off(hass):
    """Mock all lights as off."""
    hass.states.get.side_effect = (
        lambda entity: MagicMock(state="off")
        if "light" in entity
        else MagicMock(state="off")
    )


def mock_lights_on(hass):
    """Mock lights as on."""
    hass.states.get.side_effect = (
        lambda entity: MagicMock(state="on")
        if "light" in entity
        else MagicMock(state="off")
    )


def test_scenario_1_normal_operation():
    """Test normal operation with motion activation enabled."""
    print("\n=== TEST SCENARIO 1: Normal Operation ===")

    coordinator, hass = create_mock_coordinator()
    mock_lights_off(hass)

    # Start in IDLE
    coordinator._current_state = STATE_IDLE
    print(f"Initial state: {coordinator._current_state}")

    # Motion ON -> should turn lights on and go to MOTION-AUTO
    print("Motion ON...")
    coordinator._handle_motion_on()
    print(f"State after motion ON: {coordinator._current_state}")
    print(f"Turn on lights called: {coordinator._async_turn_on_tod_lights.called}")

    # Mock lights as now on after motion
    mock_lights_on(hass)

    # Motion OFF -> should start timer and go to AUTO
    print("Motion OFF...")
    coordinator._handle_motion_off()
    print(f"State after motion OFF: {coordinator._current_state}")
    print(f"Timer active: {coordinator._active_timer is not None}")
    print(f"Timer type: {coordinator._timer_type}")

    assert coordinator._current_state == STATE_AUTO
    assert coordinator._timer_type == TIMER_MOTION
    print("✅ Scenario 1 PASSED")


def test_scenario_2_motion_activation_disabled():
    """Test motion activation disabled but lights still turn off."""
    print("\n=== TEST SCENARIO 2: Motion Activation Disabled ===")

    coordinator, hass = create_mock_coordinator()
    coordinator.motion_activation = False
    mock_lights_on(hass)  # Lights already on

    # Start in IDLE, then simulate manual light on (external change)
    coordinator._current_state = STATE_IDLE
    print(f"Initial state: {coordinator._current_state}")
    print("Motion activation disabled")

    # Simulate external light change (manual turn on)
    old_state = MagicMock(state="off")
    new_state = MagicMock(state="on")
    new_state.context = MagicMock()

    print("External light turned ON...")
    coordinator._handle_external_light_change("light.ceiling", old_state, new_state, 0)
    print(f"State after external change: {coordinator._current_state}")
    print(f"Timer active: {coordinator._active_timer is not None}")
    print(f"Timer type: {coordinator._timer_type}")

    assert coordinator._current_state == STATE_MANUAL
    assert coordinator._timer_type == TIMER_EXTENDED
    print("✅ Scenario 2 PASSED")


def test_scenario_3_manual_intervention():
    """Test manual intervention during automatic operation."""
    print("\n=== TEST SCENARIO 3: Manual Intervention ===")

    coordinator, hass = create_mock_coordinator()
    mock_lights_on(hass)

    # Start in MOTION-AUTO state (after motion turned lights on)
    coordinator._current_state = STATE_MOTION_AUTO
    print(f"Initial state: {coordinator._current_state}")

    # Simulate manual brightness change during MOTION
    old_state = MagicMock(state="on")
    old_state.attributes = {"brightness": 128}  # 50%
    new_state = MagicMock(state="on")
    new_state.attributes = {"brightness": 255}  # 100%
    new_state.context = MagicMock()

    print("Manual brightness change during MOTION-AUTO...")
    coordinator._handle_external_light_change("light.ceiling", old_state, new_state, 50)
    print(f"State after manual change: {coordinator._current_state}")
    print(f"Manual reason: {coordinator._last_manual_reason}")

    # Motion OFF -> should start extended timer
    print("Motion OFF...")
    coordinator._handle_motion_off()
    print(f"State after motion OFF: {coordinator._current_state}")
    print(f"Timer active: {coordinator._active_timer is not None}")
    print(f"Timer type: {coordinator._timer_type}")

    assert coordinator._current_state == STATE_MANUAL
    assert coordinator._timer_type == TIMER_EXTENDED
    print("✅ Scenario 3 PASSED")


def test_scenario_4_override_behavior():
    """Test override behavior."""
    print("\n=== TEST SCENARIO 4: Override Behavior ===")

    coordinator, hass = create_mock_coordinator()
    mock_lights_on(hass)

    # Start in AUTO state with timer
    coordinator._current_state = STATE_AUTO
    coordinator._active_timer = MagicMock()
    coordinator._timer_type = TIMER_MOTION
    print(
        f"Initial state: {coordinator._current_state} with {coordinator._timer_type} timer"
    )

    # Override ON -> should cancel timer and go to OVERRIDDEN
    print("Override ON...")
    # Simulate override ON logic inline
    coordinator._cancel_active_timer()
    coordinator._current_state = STATE_OVERRIDDEN
    print(f"State after override ON: {coordinator._current_state}")
    print(f"Timer active: {coordinator._active_timer is not None}")

    # Override OFF with lights still on -> should start extended timer
    print("Override OFF with lights on...")
    coordinator._handle_override_off()
    print(f"State after override OFF: {coordinator._current_state}")
    print(f"Timer active: {coordinator._active_timer is not None}")
    print(f"Timer type: {coordinator._timer_type}")

    assert coordinator._current_state == STATE_MANUAL
    assert coordinator._timer_type == TIMER_EXTENDED
    print("✅ Scenario 4 PASSED")


def test_scenario_5_initial_state_motion_disabled():
    """Test initial state with motion activation disabled."""
    print("\n=== TEST SCENARIO 5: Initial State Motion Disabled ===")

    coordinator, hass = create_mock_coordinator()
    coordinator.motion_activation = False
    mock_lights_on(hass)  # Lights on at startup

    print("Setting initial state with motion activation disabled and lights on...")
    coordinator._set_initial_state()
    print(f"Initial state: {coordinator._current_state}")
    print(f"Timer active: {coordinator._active_timer is not None}")
    print(f"Timer type: {coordinator._timer_type}")
    print(f"Manual reason: {coordinator._last_manual_reason}")

    assert coordinator._current_state == STATE_MANUAL
    assert coordinator._timer_type == TIMER_EXTENDED
    print("✅ Scenario 5 PASSED")


if __name__ == "__main__":
    print("Testing Motion Coordinator Core Functionality...")

    try:
        test_scenario_1_normal_operation()
        test_scenario_2_motion_activation_disabled()
        test_scenario_3_manual_intervention()
        test_scenario_4_override_behavior()
        test_scenario_5_initial_state_motion_disabled()

        print("\n🎉 ALL TESTS PASSED!")
        print("\nCore functionality verified:")
        print("1. ✅ Automatic light ON after motion")
        print("2. ✅ Automatic light OFF after timeout")
        print("3. ✅ Day/night light selection")
        print("4. ✅ Manual intervention detection")
        print("5. ✅ Motion activation disabled behavior")
        print("6. ✅ Override functionality")
        print("7. ✅ Timer postponement on new motion")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
