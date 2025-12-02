"""Tests for __init__.py - integration setup and unload."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant

DOMAIN = "motion_lights_automation"


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Motion Lights",
        data={},
        options={},
        entry_id="test_entry_id",
        source="user",
        unique_id=None,
        discovery_keys={},
    )


class TestIntegrationSetup:
    """Test integration setup."""

    async def test_async_setup_entry_success(
        self, hass: HomeAssistant, mock_config_entry
    ):
        """Test successful integration setup."""
        await hass.config_entries.async_add(mock_config_entry)
        await hass.async_block_till_done()

        assert mock_config_entry.state == ConfigEntryState.LOADED
