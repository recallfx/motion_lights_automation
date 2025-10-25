"""Binary sensor platform for Motion Lights Automation Rig."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
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
    """Set up the motion sensor from a config entry."""
    data = config_entry.runtime_data
    room_name = data.get(CONF_NAME, "Test Room")

    motion_sensor = MotionSensor(
        unique_id=f"{config_entry.entry_id}_motion",
        room_name=room_name,
        config_entry_id=config_entry.entry_id,
    )

    async_add_entities([motion_sensor])


class MotionSensor(BinarySensorEntity):
    """Representation of a motion sensor."""

    _attr_has_entity_name = True
    _attr_name = "Motion"
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(self, unique_id: str, room_name: str, config_entry_id: str) -> None:
        """Initialize the motion sensor."""
        self._unique_id = unique_id
        self._room_name = room_name
        self._config_entry_id = config_entry_id
        self._is_on = False

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name=f"{room_name}",
            manufacturer="Motion Lights Automation Rig",
            model="Motion Sensor",
        )

    @property
    def unique_id(self) -> str:
        """Return the unique ID."""
        return self._unique_id

    @property
    def is_on(self) -> bool:
        """Return True if motion detected."""
        # Check the shared state from the switch
        motion_state_key = f"{DOMAIN}_motion_{self._config_entry_id}"
        hass_data = self.hass.data.get(DOMAIN, {})
        return hass_data.get(motion_state_key, self._is_on)

    async def async_added_to_hass(self) -> None:
        """Register dispatcher to listen for motion state changes."""
        await super().async_added_to_hass()

        # Listen for state changes from the switch
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_motion_state_changed_{self._config_entry_id}",
                self._on_motion_state_changed,
            )
        )

    @callback
    def _on_motion_state_changed(self, state: bool) -> None:
        """Handle motion state change from switch."""
        self._is_on = state
        _LOGGER.debug("Motion state changed to: %s", state)
        self.async_write_ha_state()
