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

from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .motion_coordinator import MotionLightsCoordinator

SENSOR_DESCRIPTION = SensorEntityDescription(
    key="lighting_automation",
    name="Lighting Automation",
    icon="mdi:lightbulb-on-auto",
)

DIAGNOSTIC_SENSOR_DESCRIPTION = SensorEntityDescription(
    key="lighting_automation_diagnostics",
    name="Diagnostics",
    icon="mdi:chart-line",
    entity_category=EntityCategory.DIAGNOSTIC,
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
            ),
            MotionLightsDiagnosticSensor(
                coordinator=coordinator,
                config_entry=config_entry,
                entity_description=DIAGNOSTIC_SENSOR_DESCRIPTION,
            ),
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

        # Get actual switch states
        house_active = None
        ambient_light_low = None

        if self._coordinator.house_active:
            house_state = self._coordinator.hass.states.get(
                self._coordinator.house_active
            )
            if house_state:
                house_active = house_state.state == "on"

        if self._coordinator.ambient_light_sensor:
            sensor_state = self._coordinator.hass.states.get(
                self._coordinator.ambient_light_sensor
            )
            if sensor_state:
                # Check if it's a lux sensor or binary sensor
                unit = sensor_state.attributes.get("unit_of_measurement")
                if unit == "lx":
                    try:
                        current_lux = float(sensor_state.state)
                        # Use same hysteresis logic as coordinator
                        ambient_light_low = (
                            self._coordinator._evaluate_lux_with_hysteresis(current_lux)
                        )
                    except (ValueError, TypeError):
                        ambient_light_low = None
                else:
                    # Binary sensor - ON means low ambient light
                    ambient_light_low = sensor_state.state == "on"

        # Calculate modes based on switches
        is_dark_inside = False
        if house_active is not None:
            is_dark_inside = not house_active
        elif ambient_light_low is not None:
            is_dark_inside = ambient_light_low

        # Core debugging information - what you need to understand what's happening
        attrs: dict[str, Any] = {
            # Current Status (what's happening right now)
            "current_state": self._coordinator.current_state,
            # Timer Status (when will something happen next)
            "timer_active": time_until_action is not None,
            "time_until_action": time_until_action,
            "next_action_time": (
                (now + timedelta(seconds=time_until_action)).isoformat()
                if time_until_action
                else None
            ),
            # Configuration (is motion activation on/off, what brightness levels)
            "motion_activation_enabled": self._coordinator.is_motion_activation_enabled,
            "brightness_active": self._coordinator.brightness_active,
            "brightness_inactive": self._coordinator.brightness_inactive,
            "house_active": house_active,
            "ambient_light_low": ambient_light_low,
            "is_dark_inside": is_dark_inside,
            "no_motion_wait": self._coordinator.no_motion_wait_seconds,
            "extended_timeout": self._coordinator.extended_timeout,
            # Entities being controlled
            "motion_entity": self._coordinator.motion_entity,
            "lights": self._coordinator.lights,
            "override_switch": self._coordinator.override_switch,
            "house_active_switch": self._coordinator.house_active,
            "ambient_light_sensor": self._coordinator.ambient_light_sensor,
            "ambient_light_threshold": self._coordinator.ambient_light_threshold,
        }

        return attrs


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
            # Timer state
            "timers": timer_info,
            # Light state
            "lights_on": diagnostic_data.get("lights_on"),
            "total_lights": diagnostic_data.get("total_lights"),
            # Event log (most recent events)
            "recent_events": diagnostic_data.get("recent_events", []),
            # Configuration (from main sensor)
            "brightness_active": self._coordinator.brightness_active,
            "brightness_inactive": self._coordinator.brightness_inactive,
        }
