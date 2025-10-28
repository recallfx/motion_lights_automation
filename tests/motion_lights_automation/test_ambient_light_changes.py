"""Test ambient light sensor state changes trigger re-evaluation."""

import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_LIGHTS,
    CONF_MOTION_ENTITY,
    CONF_MOTION_ACTIVATION,
    DOMAIN,
)
from custom_components.motion_lights_automation.motion_coordinator import (
    MotionLightsCoordinator,
)


@pytest.fixture
def mock_coordinator_entry(hass):
    """Create a mock config entry for testing."""
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.const import CONF_NAME

    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Motion Lights",
        data={
            CONF_NAME: "Test Room",
            CONF_MOTION_ENTITY: ["binary_sensor.test_motion"],
            CONF_LIGHTS: ["light.test_light"],
            CONF_AMBIENT_LIGHT_SENSOR: "binary_sensor.dark_outside",
            CONF_MOTION_ACTIVATION: True,
        },
        options={},
        entry_id="test_entry_id",
        source="user",
        unique_id="test_unique_id",
        discovery_keys={},
    )


async def test_ambient_light_becomes_dark_with_motion_turns_on_lights(
    hass: HomeAssistant, mock_coordinator_entry
):
    """Test that when ambient light becomes dark and motion is active, lights turn on."""
    # Set up entities
    hass.states.async_set("binary_sensor.test_motion", STATE_ON)
    hass.states.async_set("light.test_light", STATE_OFF)
    hass.states.async_set("binary_sensor.dark_outside", STATE_OFF)  # Not dark initially

    coordinator = MotionLightsCoordinator(hass, mock_coordinator_entry)
    await coordinator.async_setup_listeners()

    # Initial state should be IDLE because it's not dark
    assert coordinator.state_machine.current_state == "idle"

    # Now make it dark - this should trigger light activation since motion is active
    hass.states.async_set("binary_sensor.dark_outside", STATE_ON)
    await hass.async_block_till_done()

    # Should transition to motion-auto and turn on lights
    assert coordinator.state_machine.current_state == "motion-auto"

    # Cleanup
    coordinator.async_cleanup_listeners()


async def test_ambient_light_becomes_bright_turns_off_auto_lights(
    hass: HomeAssistant, mock_coordinator_entry
):
    """Test that when ambient light becomes bright, auto-controlled lights turn off."""
    # Set up entities - start dark with NO motion, lights OFF
    hass.states.async_set("binary_sensor.test_motion", STATE_OFF)  # NO motion initially
    hass.states.async_set("light.test_light", STATE_OFF)
    hass.states.async_set("binary_sensor.dark_outside", STATE_ON)  # Dark initially

    coordinator = MotionLightsCoordinator(hass, mock_coordinator_entry)
    await coordinator.async_setup_listeners()

    # Should start in IDLE
    assert coordinator.state_machine.current_state == "idle"

    # Turn on motion - should transition to motion-auto
    hass.states.async_set("binary_sensor.test_motion", STATE_ON)
    await hass.async_block_till_done()

    assert coordinator.state_machine.current_state == "motion-auto"

    # Now make it bright - this should turn off the lights
    with patch.object(
        coordinator.light_controller, "turn_off_lights", new_callable=AsyncMock
    ) as mock_turn_off:
        hass.states.async_set("binary_sensor.dark_outside", STATE_OFF)
        await hass.async_block_till_done()

        # Should have called turn_off_lights
        mock_turn_off.assert_called_once()

    # Cleanup
    coordinator.async_cleanup_listeners()


async def test_ambient_light_bright_in_manual_state_doesnt_force_off(
    hass: HomeAssistant, mock_coordinator_entry
):
    """Test that when ambient becomes bright in MANUAL state, lights aren't forced off."""
    # Set up entities
    hass.states.async_set("binary_sensor.test_motion", STATE_OFF)
    hass.states.async_set("light.test_light", STATE_ON)
    hass.states.async_set("binary_sensor.dark_outside", STATE_ON)

    coordinator = MotionLightsCoordinator(hass, mock_coordinator_entry)
    await coordinator.async_setup_listeners()

    # Force to MANUAL state (user manually turned on lights)
    coordinator.state_machine.force_state("manual")

    # Now make it bright - should NOT turn off lights (they're manually controlled)
    with patch.object(
        coordinator.light_controller, "turn_off_lights", new_callable=AsyncMock
    ) as mock_turn_off:
        hass.states.async_set("binary_sensor.dark_outside", STATE_OFF)
        await hass.async_block_till_done()

        # Should NOT have called turn_off_lights
        mock_turn_off.assert_not_called()

    # Should still be in manual state
    assert coordinator.state_machine.current_state == "manual"

    # Cleanup
    coordinator.async_cleanup_listeners()


async def test_house_active_changes_adjusts_brightness(hass: HomeAssistant):
    """Test that when house active state changes, brightness is adjusted."""
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.const import CONF_NAME
    from custom_components.motion_lights_automation.const import CONF_HOUSE_ACTIVE

    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Motion Lights",
        data={
            CONF_NAME: "Test Room",
            CONF_MOTION_ENTITY: ["binary_sensor.test_motion"],
            CONF_LIGHTS: ["light.test_light"],
            CONF_AMBIENT_LIGHT_SENSOR: "binary_sensor.dark_outside",
            CONF_HOUSE_ACTIVE: "input_boolean.house_active",
            CONF_MOTION_ACTIVATION: True,
        },
        options={},
        entry_id="test_entry_id",
        source="user",
        unique_id="test_unique_id",
        discovery_keys={},
    )

    # Set up entities - start with no motion, lights OFF, dark, house inactive
    hass.states.async_set("binary_sensor.test_motion", STATE_OFF)
    hass.states.async_set("light.test_light", STATE_OFF)
    hass.states.async_set("binary_sensor.dark_outside", STATE_ON)
    hass.states.async_set("input_boolean.house_active", STATE_OFF)

    coordinator = MotionLightsCoordinator(hass, entry)
    await coordinator.async_setup_listeners()

    # Turn on motion - should transition to motion-auto
    hass.states.async_set("binary_sensor.test_motion", STATE_ON)
    await hass.async_block_till_done()

    assert coordinator.state_machine.current_state == "motion-auto"

    # Simulate lights being turned on by the automation
    hass.states.async_set("light.test_light", STATE_ON, {"brightness": 26})
    await hass.async_block_till_done()

    # Now activate house - should adjust brightness
    with patch.object(
        coordinator.light_controller, "turn_on_auto_lights", new_callable=AsyncMock
    ) as mock_turn_on:
        hass.states.async_set("input_boolean.house_active", STATE_ON)
        await hass.async_block_till_done()

        # Should have called turn_on_auto_lights to adjust brightness
        mock_turn_on.assert_called_once()

    # Cleanup
    coordinator.async_cleanup_listeners()
