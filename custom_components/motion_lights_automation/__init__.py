"""The Motion lights automation integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .motion_coordinator import MotionLightsCoordinator

_PLATFORMS: list[Platform] = [Platform.SENSOR]

SERVICE_REFRESH_TRACKING = "refresh_tracking"

SERVICE_REFRESH_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Motion lights automation from a config entry."""
    # Create motion coordinator (handles all motion and manual logic per tight specification)
    motion_coordinator = MotionLightsCoordinator(hass, entry)

    # Store coordinator in runtime_data
    entry.runtime_data = motion_coordinator

    # Set up event listeners
    await motion_coordinator.async_setup_listeners()

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    # Register refresh service
    async def handle_refresh_tracking(call: ServiceCall) -> None:
        """Handle refresh tracking service call."""
        config_entry_id = call.data["config_entry_id"]
        if config_entry_id == entry.entry_id:
            await motion_coordinator.async_refresh_light_tracking()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_TRACKING,
        handle_refresh_tracking,
        schema=SERVICE_REFRESH_SCHEMA,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Clean up coordinator
    coordinator = entry.runtime_data
    coordinator.async_cleanup_listeners()

    # Remove service if this was the last entry
    if (
        len(
            [
                e
                for e in hass.config_entries.async_entries(DOMAIN)
                if e.state.recoverable
            ]
        )
        == 1
    ):
        hass.services.async_remove(DOMAIN, SERVICE_REFRESH_TRACKING)

    # Unload platforms
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
