"""Sensor platform for Motion Lights Automation Rig."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import LIGHT_LUX
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ambient light sensor from a config entry."""
    data = config_entry.runtime_data
    room_name = data.get(CONF_NAME, "Test Room")

    ambient_light_sensor = AmbientLightSensor(
        unique_id=f"{config_entry.entry_id}_ambient_light",
        room_name=room_name,
        config_entry_id=config_entry.entry_id,
    )

    async_add_entities([ambient_light_sensor])


class AmbientLightSensor(SensorEntity):
    """Representation of an ambient light sensor with controllable lux value."""

    _attr_has_entity_name = True
    _attr_name = "Ambient light"
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = LIGHT_LUX

    def __init__(self, unique_id: str, room_name: str, config_entry_id: str) -> None:
        """Initialize the ambient light sensor."""
        self._unique_id = unique_id
        self._room_name = room_name
        self._config_entry_id = config_entry_id
        self._attr_native_value = 100.0  # Default lux value

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

    @property
    def native_value(self) -> float | None:
        """Return the current lux value."""
        # Check the shared state from hass.data
        lux_state_key = f"{DOMAIN}_lux_{self._config_entry_id}"
        hass_data = self.hass.data.get(DOMAIN, {})
        return hass_data.get(lux_state_key, self._attr_native_value)

    async def async_added_to_hass(self) -> None:
        """Register dispatcher to listen for lux value changes."""
        await super().async_added_to_hass()

        # Initialize hass.data for this integration if needed
        if DOMAIN not in self.hass.data:
            self.hass.data[DOMAIN] = {}

        # Set initial value in hass.data
        lux_state_key = f"{DOMAIN}_lux_{self._config_entry_id}"
        self.hass.data[DOMAIN][lux_state_key] = self._attr_native_value

        # Listen for state changes from the control
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_lux_changed_{self._config_entry_id}",
                self._on_lux_changed,
            )
        )

    @callback
    def _on_lux_changed(self, lux_value: float) -> None:
        """Handle lux value change."""
        self._attr_native_value = lux_value
        _LOGGER.debug("Ambient light lux changed to: %s", lux_value)
        self.async_write_ha_state()
