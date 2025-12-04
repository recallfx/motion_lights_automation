"""Sensor platform for Motion Lights Automation integration.

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

from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
            MotionLightsDiagnosticSensor(
                coordinator=coordinator,
                config_entry=config_entry,
                entity_description=SENSOR_DESCRIPTION,
            ),
        ]
    )


class MotionLightsDiagnosticSensor(SensorEntity):
    """Diagnostic sensor with detailed event logging and internal state."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MotionLightsCoordinator,
        config_entry: ConfigEntry,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the diagnostic sensor."""
        self.entity_description = entity_description
        self._coordinator = coordinator
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_{entity_description.key}"

        # Get name from config entry title or data
        name = config_entry.title
        if not name and CONF_NAME in config_entry.data:
            name = config_entry.data[CONF_NAME]
        if not name:
            name = "Motion Lights Automation"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": name,
            "manufacturer": "Motion Lights Automation",
            "model": "Lighting Automation",
            "entry_type": "service",
        }

        self._remove_listener: Callable[[], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register listener when entity is added to Home Assistant."""
        await super().async_added_to_hass()
        self._remove_listener = self._coordinator.async_add_listener(
            self._handle_coordinator_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unregister listener when entity is removed."""
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write state when coordinator updates."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        """Return last event message as the sensor state."""
        diagnostic_data = self._coordinator.get_diagnostic_data()
        return diagnostic_data.get("last_event_message", "Unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic data with event history and internal state."""
        diagnostic_data = self._coordinator.get_diagnostic_data()

        # Format timer information for display
        timers = diagnostic_data.get("timers", {})
        timer_info = {}
        for timer_name, timer_data in timers.items():
            timer_info[timer_name] = {
                "remaining_seconds": timer_data.get("remaining_seconds"),
                "end_time": timer_data.get("end_time"),
            }

        return {
            # Current state
            "current_state": diagnostic_data.get("current_state"),
            "last_transition_reason": diagnostic_data.get("last_transition_reason"),
            "last_transition_time": diagnostic_data.get("last_transition_time"),
            # Conditions
            "motion_active": diagnostic_data.get("motion_active"),
            "is_dark_inside": diagnostic_data.get("is_dark_inside"),
            "is_house_active": diagnostic_data.get("is_house_active"),
            "motion_activation_enabled": diagnostic_data.get(
                "motion_activation_enabled"
            ),
            # Startup grace period (manual detection disabled during this time)
            "startup_grace_period_active": diagnostic_data.get(
                "startup_grace_period_active"
            ),
            "startup_grace_period_remaining": diagnostic_data.get(
                "startup_grace_period_remaining"
            ),
            # Timer state
            "timers": timer_info,
            # Light state
            "lights_on": diagnostic_data.get("lights_on"),
            "total_lights": diagnostic_data.get("total_lights"),
            # Event log (most recent events)
            "recent_events": diagnostic_data.get("recent_events", []),
            "event_log": diagnostic_data.get("event_log", []),
            # Configuration (from main sensor)
            "brightness_active": self._coordinator.brightness_active,
            "brightness_inactive": self._coordinator.brightness_inactive,
        }
