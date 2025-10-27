"""Number platform for Motion Lights Automation Rig."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import LIGHT_LUX
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities from a config entry."""
    data = config_entry.runtime_data
    room_name = data.get(CONF_NAME, "Test Room")

    lux_control = LuxControlNumber(
        unique_id=f"{config_entry.entry_id}_lux_control",
        room_name=room_name,
        config_entry_id=config_entry.entry_id,
        hass=hass,
    )

    async_add_entities([lux_control])


class LuxControlNumber(NumberEntity):
    """Number entity to control the ambient light lux value."""

    _attr_has_entity_name = True
    _attr_name = "Ambient light lux"
    _attr_should_poll = False
    _attr_native_min_value = 0.0
    _attr_native_max_value = 10000.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = LIGHT_LUX
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        unique_id: str,
        room_name: str,
        config_entry_id: str,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the lux control number."""
        self._unique_id = unique_id
        self._room_name = room_name
        self._config_entry_id = config_entry_id
        self.hass = hass
        self._attr_native_value = 100.0  # Default value

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry_id)},
            name=f"{room_name}",
            manufacturer="Motion Lights Automation Rig",
            model="Test Room Simulator",
        )

    @property
    def unique_id(self) -> str:
        """Return the unique ID."""
        return self._unique_id

    async def async_set_native_value(self, value: float) -> None:
        """Set the lux value."""
        self._attr_native_value = value

        # Store the lux value in hass.data
        lux_state_key = f"{DOMAIN}_lux_{self._config_entry_id}"
        self.hass.data.setdefault(DOMAIN, {})[lux_state_key] = value

        # Notify the sensor about the change
        async_dispatcher_send(
            self.hass,
            f"{DOMAIN}_lux_changed_{self._config_entry_id}",
            value,
        )

        _LOGGER.debug("Lux value set to: %s", value)
        self.async_write_ha_state()
