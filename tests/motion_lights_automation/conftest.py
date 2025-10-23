"""Fixtures for Motion Lights Automation integration tests."""

from __future__ import annotations

from unittest.mock import MagicMock, AsyncMock, patch
from typing import Any

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME, Platform
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.helpers.device_registry import DeviceRegistry

from homeassistant.const import Platform

# Import via sys.path for custom component



from homeassistant.components.motion_lights_automation.const import (
    DOMAIN,
    CONF_MOTION_ENTITY,
    CONF_BACKGROUND_LIGHT,
    CONF_FEATURE_LIGHT,
    CONF_CEILING_LIGHT,
    CONF_OVERRIDE_SWITCH,
    CONF_NO_MOTION_WAIT,
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_DARK_OUTSIDE,
    CONF_HOUSE_ACTIVE,
    CONF_MOTION_ACTIVATION,
    CONF_EXTENDED_TIMEOUT,
    DEFAULT_NO_MOTION_WAIT,
    DEFAULT_BRIGHTNESS_ACTIVE,
    DEFAULT_BRIGHTNESS_INACTIVE,
    DEFAULT_MOTION_ACTIVATION,
    DEFAULT_EXTENDED_TIMEOUT,
    STATE_IDLE,
)


@pytest.fixture
def mock_config_data() -> dict[str, Any]:
    """Return mock configuration data."""
    return {
        CONF_NAME: "Test Motion Lights",
        CONF_MOTION_ENTITY: ["binary_sensor.motion_sensor"],
        CONF_BACKGROUND_LIGHT: ["light.background"],
        CONF_FEATURE_LIGHT: ["light.feature"],
        CONF_CEILING_LIGHT: ["light.ceiling"],
        CONF_OVERRIDE_SWITCH: "switch.override",
        CONF_NO_MOTION_WAIT: DEFAULT_NO_MOTION_WAIT,
        CONF_BRIGHTNESS_ACTIVE: DEFAULT_BRIGHTNESS_ACTIVE,
        CONF_BRIGHTNESS_INACTIVE: DEFAULT_BRIGHTNESS_INACTIVE,
        CONF_DARK_OUTSIDE: "switch.dark_outside",
        CONF_HOUSE_ACTIVE: "switch.house_active",
        CONF_MOTION_ACTIVATION: DEFAULT_MOTION_ACTIVATION,
        CONF_EXTENDED_TIMEOUT: DEFAULT_EXTENDED_TIMEOUT,
    }


@pytest.fixture
def mock_config_entry(mock_config_data: dict[str, Any]) -> ConfigEntry:
    """Return a mocked config entry."""
    entry = ConfigEntry(
        version=1,
        domain=DOMAIN,
        title=mock_config_data[CONF_NAME],
        data=mock_config_data,
        options={},
        entry_id="test_entry_id",
        state="loaded",
    )
    return entry


@pytest.fixture
def mock_motion_coordinator() -> MagicMock:
    """Return a mocked motion coordinator."""
    coordinator = MagicMock()
    coordinator.current_state = STATE_IDLE
    coordinator.current_motion_state = "off"
    coordinator.is_override_active = False
    coordinator.time_until_action = None
    coordinator.is_motion_activation_enabled = DEFAULT_MOTION_ACTIVATION
    coordinator.brightness_active = DEFAULT_BRIGHTNESS_ACTIVE
    coordinator.brightness_inactive = DEFAULT_BRIGHTNESS_INACTIVE
    coordinator.no_motion_wait_seconds = DEFAULT_NO_MOTION_WAIT
    coordinator.extended_timeout = DEFAULT_EXTENDED_TIMEOUT
    coordinator.motion_entity = "binary_sensor.motion_sensor"
    coordinator.background_light_entity = "light.background"
    coordinator.feature_light_entity = "light.feature"
    coordinator.ceiling_light_entity = "light.ceiling"
    coordinator.override_switch = "switch.override"
    coordinator.dark_outside = "switch.dark_outside"
    coordinator.house_active = "switch.house_active"
    coordinator.last_motion_time = None
    coordinator.manual_reason = None
    
    # Add async methods
    coordinator.async_add_listener = MagicMock()
    coordinator.async_remove_listener = MagicMock()
    coordinator.async_refresh_light_tracking = AsyncMock()
    
    return coordinator


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    mock_motion_coordinator: MagicMock,
) -> ConfigEntry:
    """Initialize the integration."""
    mock_config_entry.add_to_hass(hass)
    
    # Patch the coordinator creation
    with patch(
        "homeassistant.components.motion_lights_automation.MotionLightsCoordinator",
        return_value=mock_motion_coordinator,
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    
    return mock_config_entry


@pytest.fixture
def entity_registry(hass: HomeAssistant) -> EntityRegistry:
    """Get the entity registry."""
    from homeassistant.helpers import entity_registry
    return entity_registry.async_get(hass)


@pytest.fixture
def device_registry(hass: HomeAssistant) -> DeviceRegistry:
    """Get the device registry."""
    from homeassistant.helpers import device_registry
    return device_registry.async_get(hass)


@pytest.fixture
def platforms() -> list[Platform]:
    """Specify which platforms to test."""
    return [Platform.SENSOR]
