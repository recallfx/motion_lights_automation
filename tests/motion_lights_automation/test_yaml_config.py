"""Tests for YAML configuration support."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_EXTENDED_TIMEOUT,
    CONF_HOUSE_ACTIVE,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_DELAY,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
    DOMAIN,
)


@pytest.fixture
def mock_motion_sensor(hass: HomeAssistant):
    """Create a mock motion sensor."""
    hass.states.async_set("binary_sensor.test_motion", "off")
    return "binary_sensor.test_motion"


@pytest.fixture
def mock_light(hass: HomeAssistant):
    """Create a mock light."""
    hass.states.async_set("light.test_light", "off")
    return "light.test_light"


@pytest.fixture
def mock_override_switch(hass: HomeAssistant):
    """Create a mock override switch."""
    hass.states.async_set("switch.test_override", "off")
    return "switch.test_override"


@pytest.fixture
def mock_ambient_light_sensor(hass: HomeAssistant):
    """Create a mock ambient light sensor."""
    hass.states.async_set("binary_sensor.sun_below_horizon", "off")
    return "binary_sensor.sun_below_horizon"


async def test_yaml_setup_basic(
    hass: HomeAssistant, mock_motion_sensor, mock_light
) -> None:
    """Test basic YAML configuration."""
    config = {
        DOMAIN: [
            {
                "name": "Test YAML Basic",
                CONF_MOTION_ENTITY: [mock_motion_sensor],
                "lights": {
                    "ceiling": [mock_light],
                },
            }
        ]
    }

    with patch(
        "custom_components.motion_lights_automation.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

        # Verify the config flow was initiated with SOURCE_IMPORT
        assert mock_setup.call_count == 1


async def test_yaml_setup_full_config(
    hass: HomeAssistant,
    mock_motion_sensor,
    mock_light,
    mock_override_switch,
    mock_ambient_light_sensor,
) -> None:
    """Test full YAML configuration with all options."""
    hass.states.async_set("switch.house_active", "off")

    config = {
        DOMAIN: [
            {
                "name": "Test YAML Full",
                CONF_MOTION_ENTITY: [mock_motion_sensor],
                "lights": {
                    "ceiling": [mock_light],
                    "background": ["light.background"],
                    "feature": ["light.feature"],
                },
                CONF_OVERRIDE_SWITCH: [mock_override_switch],
                CONF_HOUSE_ACTIVE: ["switch.house_active"],
                CONF_AMBIENT_LIGHT_SENSOR: [mock_ambient_light_sensor],
                CONF_NO_MOTION_WAIT: 600,
                CONF_EXTENDED_TIMEOUT: 1800,
                CONF_MOTION_DELAY: 5,
                CONF_BRIGHTNESS_ACTIVE: 90,
                CONF_BRIGHTNESS_INACTIVE: 15,
                CONF_AMBIENT_LIGHT_THRESHOLD: 75,
                CONF_MOTION_ACTIVATION: False,
            }
        ]
    }

    # Create the background and feature lights
    hass.states.async_set("light.background", "off")
    hass.states.async_set("light.feature", "off")

    with patch(
        "custom_components.motion_lights_automation.async_setup_entry",
        return_value=True,
    ):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()


async def test_yaml_setup_multiple_instances(
    hass: HomeAssistant, mock_motion_sensor, mock_light
) -> None:
    """Test YAML configuration with multiple instances."""
    hass.states.async_set("binary_sensor.motion_2", "off")
    hass.states.async_set("light.light_2", "off")

    config = {
        DOMAIN: [
            {
                "name": "Test YAML Instance 1",
                CONF_MOTION_ENTITY: [mock_motion_sensor],
                "lights": {
                    "ceiling": [mock_light],
                },
            },
            {
                "name": "Test YAML Instance 2",
                CONF_MOTION_ENTITY: ["binary_sensor.motion_2"],
                "lights": {
                    "ceiling": ["light.light_2"],
                },
            },
        ]
    }

    with patch(
        "custom_components.motion_lights_automation.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

        # Both instances should be set up
        assert mock_setup.call_count == 2


async def test_yaml_setup_empty_config(hass: HomeAssistant) -> None:
    """Test YAML setup with no configuration."""
    config = {}

    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()

    # Should return True but not create any entries
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 0


async def test_yaml_import_step(
    hass: HomeAssistant, mock_motion_sensor, mock_light
) -> None:
    """Test the config flow import step."""
    from homeassistant.config_entries import ConfigFlowContext


    # Create a proper context for the flow
    context = ConfigFlowContext(source=SOURCE_IMPORT)

    import_data = {
        "name": "Test Import",
        CONF_MOTION_ENTITY: [mock_motion_sensor],
        "ceiling_light": [mock_light],
        "background_light": [],
        "feature_light": [],
        CONF_OVERRIDE_SWITCH: None,
        CONF_HOUSE_ACTIVE: None,
        CONF_AMBIENT_LIGHT_SENSOR: None,
        CONF_NO_MOTION_WAIT: 300,
        CONF_EXTENDED_TIMEOUT: 1200,
        CONF_MOTION_DELAY: 0,
        CONF_BRIGHTNESS_ACTIVE: 80,
        CONF_BRIGHTNESS_INACTIVE: 10,
        CONF_AMBIENT_LIGHT_THRESHOLD: 50,
        CONF_MOTION_ACTIVATION: True,
    }

    # Use the config entries flow manager
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context=context,
        data=import_data,
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "Test Import"


async def test_yaml_import_duplicate_prevented(
    hass: HomeAssistant, mock_motion_sensor, mock_light
) -> None:
    """Test that duplicate YAML imports are prevented."""
    from homeassistant.config_entries import ConfigFlowContext
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    # Create an existing entry with the same name
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Duplicate",
        data={},
        unique_id="Test Duplicate",
    )
    entry.add_to_hass(hass)

    # Create a proper context for the flow
    context = ConfigFlowContext(source=SOURCE_IMPORT)

    import_data = {
        "name": "Test Duplicate",
        CONF_MOTION_ENTITY: [mock_motion_sensor],
        "ceiling_light": [mock_light],
        "background_light": [],
        "feature_light": [],
        CONF_OVERRIDE_SWITCH: None,
        CONF_HOUSE_ACTIVE: None,
        CONF_AMBIENT_LIGHT_SENSOR: None,
        CONF_NO_MOTION_WAIT: 300,
        CONF_EXTENDED_TIMEOUT: 1200,
        CONF_MOTION_DELAY: 0,
        CONF_BRIGHTNESS_ACTIVE: 80,
        CONF_BRIGHTNESS_INACTIVE: 10,
        CONF_AMBIENT_LIGHT_THRESHOLD: 50,
        CONF_MOTION_ACTIVATION: True,
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context=context,
        data=import_data,
    )

    # Should abort because of duplicate unique_id
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
