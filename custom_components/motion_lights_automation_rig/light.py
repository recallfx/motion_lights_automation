"""Light platform for Motion Lights Automation Rig."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity, LightEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the lights from a config entry."""
    data = config_entry.runtime_data
    room_name = data.get(CONF_NAME, "Test Room")

    lights = [
        TestLight(
            unique_id=f"{config_entry.entry_id}_ceiling",
            name="Ceiling Light",
            room_name=room_name,
        ),
        TestLight(
            unique_id=f"{config_entry.entry_id}_background",
            name="Background Light",
            room_name=room_name,
        ),
        TestLight(
            unique_id=f"{config_entry.entry_id}_feature",
            name="Feature Light",
            room_name=room_name,
        ),
    ]

    async_add_entities(lights)


class TestLight(LightEntity):
    """Representation of a test light."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(self, unique_id: str, name: str, room_name: str) -> None:
        """Initialize the light."""
        self._unique_id = unique_id
        self._attr_name = name
        self._room_name = room_name
        self._is_on = False
        self._brightness = 255

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name=f"{room_name}",
            manufacturer="Motion Lights Automation Rig",
            model="Test Light",
        )

    @property
    def unique_id(self) -> str:
        """Return the unique ID."""
        return self._unique_id

    @property
    def is_on(self) -> bool:
        """Return True if light is on."""
        return self._is_on

    @property
    def brightness(self) -> int:
        """Return the brightness of the light."""
        return self._brightness

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        self._is_on = True

        if "brightness" in kwargs:
            self._brightness = kwargs["brightness"]

        _LOGGER.debug(
            "%s turned on with brightness: %d",
            self._attr_name,
            self._brightness,
        )

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        self._is_on = False

        _LOGGER.debug("%s turned off", self._attr_name)

        self.async_write_ha_state()
