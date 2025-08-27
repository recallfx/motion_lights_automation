"""Test the simplified configuration with single combined light."""

from .const import (
    CONF_BRIGHTNESS_DAY,
    CONF_BRIGHTNESS_NIGHT,
    CONF_COMBINED_LIGHT,
    CONF_EXTENDED_TIMEOUT,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
)
from .motion_coordinator import MotionLightsCoordinator
import asyncio


def test_simplified_config():
    """Test that the simplified configuration loads correctly."""

    # Create test configuration
    test_config = {
        CONF_MOTION_ENTITY: "binary_sensor.motion_study",
        CONF_COMBINED_LIGHT: "light.study_combined",
        CONF_OVERRIDE_SWITCH: "input_boolean.study_override",
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
            # Minimal loop/task support used by DataUpdateCoordinator and coordinator
            self.loop = asyncio.get_event_loop()
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
    assert coordinator.combined_light == "light.study_combined"
    assert coordinator.motion_entity == "binary_sensor.motion_study"
    assert coordinator.override_switch == "input_boolean.study_override"
    assert coordinator.motion_activation
    assert coordinator.brightness_day == 60
    assert coordinator.brightness_night == 10

    # Test property methods
    assert coordinator.combined_light_entity == "light.study_combined"
    assert coordinator.is_motion_activation_enabled
    assert coordinator.day_brightness == 60
    assert coordinator.night_brightness == 10

    # Smoke-check: coordinator exposes data dict and properties without raising
    assert isinstance(coordinator.data, dict)
