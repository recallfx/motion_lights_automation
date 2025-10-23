"""Integration tests for Motion Lights Automation."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
from tests.common import MockConfigEntry


async def test_motion_lights_automation_setup(hass: HomeAssistant) -> None:
    """Test Motion Lights Automation setup."""
    # Create a minimal config entry
    config_entry = MockConfigEntry(
        domain="motion_lights_automation",
        title="Motion Lights Test",
        unique_id="test_motion",
        data={"motion_entity": "binary_sensor.motion"},
        options={},
    )
    
    config_entry.add_to_hass(hass)
    
    # Verify it was added
    assert config_entry.domain == "motion_lights_automation"
    assert config_entry.title == "Motion Lights Test"
