"""Sensor platform for Motion Lights Advanced integration.

This module exposes a single sensor that provides essential status and debugging
information for the motion-activated lighting automation system:

Core Status:
- Current state (overridden, idle, motion-auto, motion-manual, auto, manual, manual-off)
- Motion detection and override status
- Timer information and next timeout

Debugging Info:
- Manual intervention reasons (why did it go manual?)
- Configuration settings (motion activation, brightness levels)
- Entity assignments (motion sensor, combined light, override switch)
- Basic statistics (motion count, last motion time)

The sensor reflects the state of the unified motion coordinator with simplified
attributes focused on what's actually useful for troubleshooting.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .motion_coordinator import MotionLightsCoordinator

SENSOR_DESCRIPTION = SensorEntityDescription(
    key="lighting_automation",
    name="Lighting Automation",
    icon="mdi:lightbulb-on-auto",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator = config_entry.runtime_data

    async_add_entities(
        [
            MotionLightsSensor(
                coordinator=coordinator,
                config_entry=config_entry,
                entity_description=SENSOR_DESCRIPTION,
            )
        ]
    )


class MotionLightsSensor(SensorEntity):
    """Sensor representing motion-activated lighting automation status."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MotionLightsCoordinator,
        config_entry: ConfigEntry,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the motion lights sensor."""
        self.entity_description = entity_description
        self._coordinator = coordinator
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": config_entry.data[CONF_NAME],
            "manufacturer": "Motion Lights Advanced",
            "model": "Lighting Automation",
            "entry_type": "service",
        }

        # Register update listener
        self._coordinator.async_add_listener(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write state when coordinator updates."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        """Return current state of the lighting automation."""
        return self._coordinator.current_state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return essential attributes for debugging and status."""
        now = dt_util.now()
        time_until_action = self._coordinator.time_until_action

        # Core debugging information - what you need to understand what's happening
        attrs: dict[str, Any] = {
            # Current Status (what's happening right now)
            "current_state": self._coordinator.current_state,
            "motion_detected": self._coordinator.current_motion_state == "on",
            "override_active": self._coordinator.is_override_active,
            # Timer Status (when will something happen next)
            "timer_active": time_until_action is not None,
            "time_until_action": time_until_action,
            "next_action_time": (now + timedelta(seconds=time_until_action)).isoformat()
            if time_until_action
            else None,
            # Why are we in manual state? (most common debugging question)
            "manual_reason": getattr(self._coordinator, "manual_reason", None),
            # Configuration (is motion activation on/off, what brightness levels)
            "motion_activation_enabled": self._coordinator.is_motion_activation_enabled,
            "day_brightness": self._coordinator.day_brightness,
            "night_brightness": self._coordinator.night_brightness,
            "no_motion_wait": self._coordinator.no_motion_wait_seconds,
            "extended_timeout": self._coordinator.extended_timeout,
            # Entities being controlled
            "motion_entity": self._coordinator.motion_entity,
            "background_light": self._coordinator.background_light_entity,
            "feature_light": self._coordinator.feature_light_entity,
            "ceiling_light": self._coordinator.ceiling_light_entity,
            "override_switch": self._coordinator.override_switch,
            # Simple stats (how many times motion detected, when was last time)
            "last_motion_time": self._coordinator.last_motion_time.isoformat()
            if self._coordinator.last_motion_time
            else None,
        }

        return attrs
