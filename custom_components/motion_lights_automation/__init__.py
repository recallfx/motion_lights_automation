"""The Motion lights automation integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import Platform, CONF_NAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    CONF_MOTION_ENTITY,
    CONF_LIGHTS,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_HOUSE_ACTIVE,
    CONF_MOTION_ACTIVATION,
    CONF_EXTENDED_TIMEOUT,
    CONF_MOTION_DELAY,
    DEFAULT_NO_MOTION_WAIT,
    DEFAULT_BRIGHTNESS_ACTIVE,
    DEFAULT_BRIGHTNESS_INACTIVE,
    DEFAULT_AMBIENT_LIGHT_THRESHOLD,
    DEFAULT_MOTION_ACTIVATION,
    DEFAULT_EXTENDED_TIMEOUT,
    DEFAULT_MOTION_DELAY,
)
from .motion_coordinator import MotionLightsCoordinator

_LOGGER = logging.getLogger(__name__)

_PLATFORMS: list[Platform] = [Platform.SENSOR]

# YAML configuration schema
AUTOMATION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_MOTION_ENTITY): cv.entity_ids,
        vol.Required(CONF_LIGHTS): cv.entity_ids,
        vol.Optional(CONF_OVERRIDE_SWITCH): cv.entity_ids,
        vol.Optional(CONF_HOUSE_ACTIVE): cv.entity_ids,
        vol.Optional(CONF_AMBIENT_LIGHT_SENSOR): cv.entity_id,
        vol.Optional(
            CONF_NO_MOTION_WAIT, default=DEFAULT_NO_MOTION_WAIT
        ): cv.positive_int,
        vol.Optional(
            CONF_EXTENDED_TIMEOUT, default=DEFAULT_EXTENDED_TIMEOUT
        ): cv.positive_int,
        vol.Optional(CONF_MOTION_DELAY, default=DEFAULT_MOTION_DELAY): vol.All(
            cv.positive_int, vol.Range(min=0, max=30)
        ),
        vol.Optional(
            CONF_BRIGHTNESS_ACTIVE, default=DEFAULT_BRIGHTNESS_ACTIVE
        ): vol.All(cv.positive_int, vol.Range(min=0, max=100)),
        vol.Optional(
            CONF_BRIGHTNESS_INACTIVE, default=DEFAULT_BRIGHTNESS_INACTIVE
        ): vol.All(cv.positive_int, vol.Range(min=0, max=100)),
        vol.Optional(
            CONF_AMBIENT_LIGHT_THRESHOLD, default=DEFAULT_AMBIENT_LIGHT_THRESHOLD
        ): vol.All(cv.positive_int, vol.Range(min=10, max=500)),
        vol.Optional(
            CONF_MOTION_ACTIVATION, default=DEFAULT_MOTION_ACTIVATION
        ): cv.boolean,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.All(cv.ensure_list, [AUTOMATION_SCHEMA])},
    extra=vol.ALLOW_EXTRA,
)

SERVICE_REFRESH_TRACKING = "refresh_tracking"

SERVICE_REFRESH_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Motion Lights Automation component from YAML."""
    if DOMAIN not in config:
        return True

    for automation_config in config[DOMAIN]:
        name = automation_config[CONF_NAME]

        # Check if this automation already exists (by name)
        existing_entries = hass.config_entries.async_entries(DOMAIN)
        if any(entry.title == name for entry in existing_entries):
            _LOGGER.info(
                "Motion Lights Automation '%s' already exists, skipping YAML import",
                name,
            )
            continue

        # Convert list fields to single values if they have exactly one element
        # to match the config_flow expectations
        import_config = automation_config.copy()
        for key in [CONF_OVERRIDE_SWITCH, CONF_HOUSE_ACTIVE, CONF_AMBIENT_LIGHT_SENSOR]:
            if (
                isinstance(import_config.get(key), list)
                and len(import_config[key]) == 1
            ):
                import_config[key] = import_config[key][0]
            elif (
                isinstance(import_config.get(key), list)
                and len(import_config[key]) == 0
            ):
                import_config[key] = None

        # Create a config entry from YAML
        _LOGGER.info("Importing Motion Lights Automation '%s' from YAML", name)
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=import_config,
            )
        )

    return True


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
    # Clean up coordinator (only if it was set up)
    if hasattr(entry, "runtime_data") and entry.runtime_data:
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
