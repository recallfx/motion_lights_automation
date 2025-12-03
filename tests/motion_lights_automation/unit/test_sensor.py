"""Tests for Motion Lights Automation sensor."""

from __future__ import annotations

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.motion_lights_automation.const import (
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_EXTENDED_TIMEOUT,
    CONF_LIGHTS,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    DOMAIN,
)
from custom_components.motion_lights_automation.sensor import (
    MotionLightsDiagnosticSensor,
    SENSOR_DESCRIPTION,
)


class TestMotionLightsDiagnosticSensor:
    """Test the actual MotionLightsDiagnosticSensor class."""

    async def test_sensor_creation(self, hass: HomeAssistant) -> None:
        """Test sensor is created with correct attributes."""
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.test"],
                CONF_NO_MOTION_WAIT: 300,
                CONF_EXTENDED_TIMEOUT: 1200,
                CONF_BRIGHTNESS_ACTIVE: 80,
                CONF_BRIGHTNESS_INACTIVE: 20,
                CONF_MOTION_ACTIVATION: True,
            },
            entry_id="test_sensor_creation",
            title="Living Room",
        )

        # Set up mock entities
        hass.states.async_set("binary_sensor.motion", STATE_OFF)
        hass.states.async_set("light.test", STATE_OFF)

        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        # Get the sensor entity
        sensor_entity_id = "sensor.living_room_lighting_automation"
        sensor_state = hass.states.get(sensor_entity_id)

        assert sensor_state is not None
        assert sensor_state.attributes.get("brightness_active") == 80
        assert sensor_state.attributes.get("brightness_inactive") == 20

        # Cleanup
        coordinator = config_entry.runtime_data
        coordinator.async_cleanup_listeners()

    async def test_sensor_unique_id(self, hass: HomeAssistant) -> None:
        """Test sensor has correct unique ID format."""
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.test"],
                CONF_NO_MOTION_WAIT: 300,
                CONF_EXTENDED_TIMEOUT: 1200,
                CONF_BRIGHTNESS_ACTIVE: 100,
                CONF_BRIGHTNESS_INACTIVE: 30,
                CONF_MOTION_ACTIVATION: True,
            },
            entry_id="unique_test_entry",
            title="Test Room",
        )

        hass.states.async_set("binary_sensor.motion", STATE_OFF)
        hass.states.async_set("light.test", STATE_OFF)

        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        # Get coordinator and check sensor unique_id format
        coordinator = config_entry.runtime_data
        sensor = MotionLightsDiagnosticSensor(
            coordinator=coordinator,
            config_entry=config_entry,
            entity_description=SENSOR_DESCRIPTION,
        )

        assert sensor.unique_id == "unique_test_entry_lighting_automation"

        coordinator.async_cleanup_listeners()

    async def test_sensor_device_info(self, hass: HomeAssistant) -> None:
        """Test sensor has correct device info."""
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.test"],
                CONF_NO_MOTION_WAIT: 300,
                CONF_EXTENDED_TIMEOUT: 1200,
                CONF_BRIGHTNESS_ACTIVE: 100,
                CONF_BRIGHTNESS_INACTIVE: 30,
                CONF_MOTION_ACTIVATION: True,
            },
            entry_id="device_info_test",
            title="Kitchen Lights",
        )

        hass.states.async_set("binary_sensor.motion", STATE_OFF)
        hass.states.async_set("light.test", STATE_OFF)

        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        coordinator = config_entry.runtime_data
        sensor = MotionLightsDiagnosticSensor(
            coordinator=coordinator,
            config_entry=config_entry,
            entity_description=SENSOR_DESCRIPTION,
        )

        device_info = sensor.device_info
        assert device_info["name"] == "Kitchen Lights"
        assert device_info["manufacturer"] == "Motion Lights Automation"
        assert device_info["model"] == "Lighting Automation"
        assert (DOMAIN, "device_info_test") in device_info["identifiers"]

        coordinator.async_cleanup_listeners()

    async def test_sensor_native_value_shows_last_event(
        self, hass: HomeAssistant
    ) -> None:
        """Test sensor native_value shows last event message."""
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.test"],
                CONF_NO_MOTION_WAIT: 300,
                CONF_EXTENDED_TIMEOUT: 1200,
                CONF_BRIGHTNESS_ACTIVE: 100,
                CONF_BRIGHTNESS_INACTIVE: 30,
                CONF_MOTION_ACTIVATION: True,
            },
            entry_id="native_value_test",
            title="Test",
        )

        hass.states.async_set("binary_sensor.motion", STATE_OFF)
        hass.states.async_set("light.test", STATE_OFF)

        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        sensor_entity_id = "sensor.test_lighting_automation"
        sensor_state = hass.states.get(sensor_entity_id)

        # After startup, should show "Integration restarted" message
        assert "Integration restarted" in sensor_state.state

        coordinator = config_entry.runtime_data
        coordinator.async_cleanup_listeners()

    async def test_sensor_extra_state_attributes(self, hass: HomeAssistant) -> None:
        """Test sensor has all required extra_state_attributes."""
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.test"],
                CONF_NO_MOTION_WAIT: 300,
                CONF_EXTENDED_TIMEOUT: 1200,
                CONF_BRIGHTNESS_ACTIVE: 100,
                CONF_BRIGHTNESS_INACTIVE: 30,
                CONF_MOTION_ACTIVATION: True,
            },
            entry_id="attrs_test",
            title="Test",
        )

        hass.states.async_set("binary_sensor.motion", STATE_OFF)
        hass.states.async_set("light.test", STATE_OFF)

        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        sensor_entity_id = "sensor.test_lighting_automation"
        sensor_state = hass.states.get(sensor_entity_id)

        # Verify required attributes exist
        required_attrs = [
            "current_state",
            "motion_active",
            "motion_activation_enabled",
            "brightness_active",
            "brightness_inactive",
            "timers",
            "lights_on",
            "total_lights",
            "event_log",
        ]

        for attr in required_attrs:
            assert attr in sensor_state.attributes, f"Missing attribute: {attr}"

        coordinator = config_entry.runtime_data
        coordinator.async_cleanup_listeners()

    async def test_sensor_updates_on_coordinator_change(
        self, hass: HomeAssistant
    ) -> None:
        """Test sensor updates when coordinator state changes."""
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.test"],
                CONF_NO_MOTION_WAIT: 300,
                CONF_EXTENDED_TIMEOUT: 1200,
                CONF_BRIGHTNESS_ACTIVE: 100,
                CONF_BRIGHTNESS_INACTIVE: 30,
                CONF_MOTION_ACTIVATION: True,
            },
            entry_id="update_test",
            title="Test",
        )

        hass.states.async_set("binary_sensor.motion", STATE_OFF)
        hass.states.async_set("light.test", STATE_OFF)

        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        sensor_entity_id = "sensor.test_lighting_automation"

        # Get initial state
        initial_state = hass.states.get(sensor_entity_id)
        initial_current_state = initial_state.attributes.get("current_state")
        assert initial_current_state == "standby"

        # Trigger motion - should change state
        hass.states.async_set("binary_sensor.motion", STATE_ON)
        await hass.async_block_till_done()

        # Sensor should now show new state
        updated_state = hass.states.get(sensor_entity_id)
        updated_current_state = updated_state.attributes.get("current_state")
        assert updated_current_state == "motion-detected"

        coordinator = config_entry.runtime_data
        coordinator.async_cleanup_listeners()

    async def test_sensor_has_entity_name_flag(self, hass: HomeAssistant) -> None:
        """Test sensor uses has_entity_name correctly."""
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.test"],
                CONF_NO_MOTION_WAIT: 300,
                CONF_EXTENDED_TIMEOUT: 1200,
                CONF_BRIGHTNESS_ACTIVE: 100,
                CONF_BRIGHTNESS_INACTIVE: 30,
                CONF_MOTION_ACTIVATION: True,
            },
            entry_id="entity_name_test",
            title="Test",
        )

        hass.states.async_set("binary_sensor.motion", STATE_OFF)
        hass.states.async_set("light.test", STATE_OFF)

        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        coordinator = config_entry.runtime_data
        sensor = MotionLightsDiagnosticSensor(
            coordinator=coordinator,
            config_entry=config_entry,
            entity_description=SENSOR_DESCRIPTION,
        )

        # Verify has_entity_name is True (required for proper naming)
        assert sensor.has_entity_name is True

        coordinator.async_cleanup_listeners()

    async def test_sensor_motion_active_reflects_sensor_state(
        self, hass: HomeAssistant
    ) -> None:
        """Test motion_active attribute reflects actual motion sensor state."""
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.test"],
                CONF_NO_MOTION_WAIT: 300,
                CONF_EXTENDED_TIMEOUT: 1200,
                CONF_BRIGHTNESS_ACTIVE: 100,
                CONF_BRIGHTNESS_INACTIVE: 30,
                CONF_MOTION_ACTIVATION: True,
            },
            entry_id="motion_active_test",
            title="Test",
        )

        hass.states.async_set("binary_sensor.motion", STATE_OFF)
        hass.states.async_set("light.test", STATE_OFF)

        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        sensor_entity_id = "sensor.test_lighting_automation"

        # Initially motion is off
        sensor_state = hass.states.get(sensor_entity_id)
        assert sensor_state.attributes.get("motion_active") is False

        # Turn motion on
        hass.states.async_set("binary_sensor.motion", STATE_ON)
        await hass.async_block_till_done()

        sensor_state = hass.states.get(sensor_entity_id)
        assert sensor_state.attributes.get("motion_active") is True

        # Turn motion off
        hass.states.async_set("binary_sensor.motion", STATE_OFF)
        await hass.async_block_till_done()

        sensor_state = hass.states.get(sensor_entity_id)
        assert sensor_state.attributes.get("motion_active") is False

        coordinator = config_entry.runtime_data
        coordinator.async_cleanup_listeners()
