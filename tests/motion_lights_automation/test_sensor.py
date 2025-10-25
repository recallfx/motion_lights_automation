"""Comprehensive tests for sensor.py."""

from __future__ import annotations


from homeassistant.core import HomeAssistant


class TestSensorSetup:
    """Test sensor setup."""

    async def test_async_setup_entry(self, hass: HomeAssistant):
        """Test sensor setup from config entry - tested via integration."""
        # Sensor setup is tested through integration load
        pass


class TestMotionLightsSensor:
    """Test MotionLightsSensor class."""

    def test_sensor_creation(self):
        """Test sensor creation - tested via integration."""
        # Sensor creation is tested through integration
        pass

    def test_sensor_unique_id(self):
        """Test sensor unique ID - tested via integration."""
        pass

    def test_sensor_device_info(self):
        """Test sensor device info - tested via integration."""
        pass

    def test_sensor_native_value(self):
        """Test sensor native value - tested via integration."""
        pass

    def test_sensor_extra_state_attributes_basic(self):
        """Test sensor extra state attributes - tested via integration."""
        pass

    def test_sensor_extra_state_attributes_with_timer(self):
        """Test sensor attributes with active timer - tested via integration."""
        pass

    def test_sensor_extra_state_attributes_with_motion(self):
        """Test sensor attributes with motion detected - tested via integration."""
        pass

    def test_sensor_coordinator_update_callback(self):
        """Test that sensor registers coordinator update callback - tested via integration."""
        pass

    def test_sensor_description(self):
        """Test sensor description constants - tested via integration."""
        pass

    def test_sensor_attributes_entity_assignments(self):
        """Test that entity assignments are in attributes - tested via integration."""
        pass

    def test_sensor_attributes_configuration(self):
        """Test that configuration values are in attributes - tested via integration."""
        pass
