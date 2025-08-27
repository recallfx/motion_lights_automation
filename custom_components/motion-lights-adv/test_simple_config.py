"""Test the configuration with three separate light entities."""

import asyncio

from .const import (
    CONF_BACKGROUND_LIGHT,
    CONF_BRIGHTNESS_DAY,
    CONF_BRIGHTNESS_NIGHT,
    CONF_CEILING_LIGHT,
    CONF_DARK_OUTSIDE,
    CONF_EXTENDED_TIMEOUT,
    CONF_FEATURE_LIGHT,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
)
from .motion_coordinator import MotionLightsCoordinator


def test_simplified_config():
    """Test that the configuration loads correctly."""

    # Create test configuration
    test_config = {
        CONF_MOTION_ENTITY: "binary_sensor.motion_study",
        CONF_BACKGROUND_LIGHT: "light.study_background",
        CONF_FEATURE_LIGHT: "light.study_feature",
        CONF_CEILING_LIGHT: "light.study_ceiling",
        CONF_OVERRIDE_SWITCH: "input_boolean.study_override",
        CONF_DARK_OUTSIDE: "binary_sensor.dark_outside",
        CONF_MOTION_ACTIVATION: True,
        CONF_NO_MOTION_WAIT: 120,
        CONF_EXTENDED_TIMEOUT: 600,
        CONF_BRIGHTNESS_DAY: 60,
        CONF_BRIGHTNESS_NIGHT: 10,
    }

    # Mock Home Assistant object
    class MockHass:
        def __init__(self):
            self.states = MockStates()
            # Use modern asyncio pattern for loop/task support
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
            self.async_create_task = lambda coro: self.loop.create_task(coro)

    class MockStates:
        def get(self, entity_id):
            # Return mock state objects for our test entities
            class MockState:
                def __init__(self, entity_id):
                    self.entity_id = entity_id
                    self.state = "off"
                    self.attributes = {"brightness": 0}

            return MockState(entity_id)

    # Create coordinator with simplified config
    hass = MockHass()

    class MockEntry:
        def __init__(self, data):
            self.data = data
            self._unloads = []

        def async_on_unload(self, func):
            self._unloads.append(func)
            return func

    # Provide a config entry-like object
    coordinator = MotionLightsCoordinator(hass, MockEntry(test_config))

    # Test configuration properties
    assert coordinator.background_light == "light.study_background"
    assert coordinator.feature_light == "light.study_feature"
    assert coordinator.ceiling_light == "light.study_ceiling"
    assert coordinator.motion_entity == "binary_sensor.motion_study"
    assert coordinator.override_switch == "input_boolean.study_override"
    assert coordinator.dark_outside == "binary_sensor.dark_outside"
    assert coordinator.motion_activation
    assert coordinator.brightness_day == 60
    assert coordinator.brightness_night == 10

    # Test property methods
    assert coordinator.background_light_entity == "light.study_background"
    assert coordinator.feature_light_entity == "light.study_feature"
    assert coordinator.ceiling_light_entity == "light.study_ceiling"
    assert coordinator.is_motion_activation_enabled
    assert coordinator.day_brightness == 60
    assert coordinator.night_brightness == 10

    # Smoke-check: coordinator exposes data dict and properties without raising
    assert isinstance(coordinator.data, dict)
