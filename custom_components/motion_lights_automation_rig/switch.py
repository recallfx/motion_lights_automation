"""Switch platform for Motion Lights Automation Rig."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
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
    """Set up the switches from a config entry."""
    data = config_entry.runtime_data
    room_name = data.get(CONF_NAME, "Test Room")

    switches = [
        MotionToggleSwitch(
            unique_id=f"{config_entry.entry_id}_motion_toggle",
            name="Motion Toggle",
            room_name=room_name,
            icon="mdi:motion-sensor",
            hass=hass,
            config_entry_id=config_entry.entry_id,
        ),
        TestSwitch(
            unique_id=f"{config_entry.entry_id}_override",
            name="Override Switch",
            room_name=room_name,
            icon="mdi:toggle-switch",
        ),
        TestSwitch(
            unique_id=f"{config_entry.entry_id}_dark_inside",
            name="Dark Inside",
            room_name=room_name,
            icon="mdi:moon-waning-crescent",
        ),
        TestSwitch(
            unique_id=f"{config_entry.entry_id}_house_active",
            name="House Active",
            room_name=room_name,
            icon="mdi:home-account",
        ),
    ]

    async_add_entities(switches)


class MotionToggleSwitch(SwitchEntity):
    """Motion toggle switch that controls the motion sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        unique_id: str,
        name: str,
        room_name: str,
        icon: str,
        hass: HomeAssistant,
        config_entry_id: str,
    ) -> None:
        """Initialize the motion toggle switch."""
        self._unique_id = unique_id
        self._attr_name = name
        self._room_name = room_name
        self._attr_icon = icon
        self._is_on = False
        self.hass = hass
        self._config_entry_id = config_entry_id

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name=f"{room_name}",
            manufacturer="Motion Lights Automation Rig",
            model="Motion Toggle",
        )

    @property
    def unique_id(self) -> str:
        """Return the unique ID."""
        return self._unique_id

    @property
    def is_on(self) -> bool:
        """Return True if switch is on (motion active)."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn motion on."""
        self._is_on = True
        
        # Store motion state in hass.data so the sensor can access it
        motion_state_key = f"{DOMAIN}_motion_{self._config_entry_id}"
        self.hass.data.setdefault(DOMAIN, {})[motion_state_key] = True
        
        # Notify any listeners that the state changed
        async_dispatcher_send(
            self.hass,
            f"{DOMAIN}_motion_state_changed_{self._config_entry_id}",
            True,
        )
        
        _LOGGER.debug("Motion activated via toggle")
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn motion off."""
        self._is_on = False
        
        # Store motion state in hass.data so the sensor can access it
        motion_state_key = f"{DOMAIN}_motion_{self._config_entry_id}"
        self.hass.data.setdefault(DOMAIN, {})[motion_state_key] = False
        
        # Notify any listeners that the state changed
        async_dispatcher_send(
            self.hass,
            f"{DOMAIN}_motion_state_changed_{self._config_entry_id}",
            False,
        )
        
        _LOGGER.debug("Motion deactivated via toggle")
        self.async_write_ha_state()


class TestSwitch(SwitchEntity):
    """Representation of a test switch."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        unique_id: str,
        name: str,
        room_name: str,
        icon: str,
    ) -> None:
        """Initialize the switch."""
        self._unique_id = unique_id
        self._attr_name = name
        self._room_name = room_name
        self._attr_icon = icon
        self._is_on = False

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name=f"{room_name}",
            manufacturer="Motion Lights Automation Rig",
            model="Test Switch",
        )

    @property
    def unique_id(self) -> str:
        """Return the unique ID."""
        return self._unique_id

    @property
    def is_on(self) -> bool:
        """Return True if switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        self._is_on = True
        _LOGGER.debug("%s turned on", self._attr_name)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        self._is_on = False
        _LOGGER.debug("%s turned off", self._attr_name)
        self.async_write_ha_state()
