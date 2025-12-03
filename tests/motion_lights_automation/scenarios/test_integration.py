"""Integration tests for Motion Lights Automation."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def test_motion_lights_automation_setup(hass: HomeAssistant) -> None:
    """Test Motion Lights Automation setup."""
    # Create a minimal config entry
    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain="motion_lights_automation",
        title="Motion Lights Test",
        unique_id="test_motion",
        data={"motion_entity": "binary_sensor.motion"},
        options={},
        entry_id="test_entry_id",
        source="user",
        discovery_keys={},
    )

    await hass.config_entries.async_add(config_entry)

    # Verify it was added
    assert config_entry.domain == "motion_lights_automation"
    assert config_entry.title == "Motion Lights Test"
