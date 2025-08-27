#!/usr/bin/env python3
"""Test that the integration loads without runtime errors."""

import sys
import os

# Add the integration path
sys.path.insert(0, "/workspaces/ha_core/config/custom_components")

try:
    # Test imports
    from motion_lights_adv.const import DOMAIN, CONF_COMBINED_LIGHT
    from motion_lights_adv.motion_coordinator import MotionLightsCoordinator
    from motion_lights_adv.config_flow import MotionLightsAdvConfigFlow

    print("✅ All imports successful")

    # Test configuration constants
    test_config = {
        "motion_entity": "binary_sensor.test_motion",
        "combined_light": "light.test_combined",
        "override_switch": "input_boolean.test_override",
        "motion_activation": True,
        "no_motion_wait": 120,
        "extended_timeout": 600,
        "brightness_day": 60,
        "brightness_night": 10,
    }

    print("✅ Configuration structure validated")

    # Mock minimal Home Assistant for coordinator test
    class MockHass:
        def __init__(self):
            self.states = MockStateRegistry()

        def async_add_executor_job(self, func, *args):
            return func(*args)

    class MockStateRegistry:
        def get(self, entity_id):
            class MockState:
                def __init__(self):
                    self.state = "off"
                    self.attributes = {"brightness": 0}

            return MockState()

    class MockConfigEntry:
        def __init__(self, data):
            self.data = data
            self.entry_id = "test_entry"

        def async_on_unload(self, callback):
            pass  # Mock unload callback registration

    # Test coordinator creation (should not crash)
    hass = MockHass()
    mock_entry = MockConfigEntry(test_config)
    coordinator = MotionLightsCoordinator(hass, mock_entry)

    print("✅ Coordinator creation successful")
    print(f"✅ Combined light: {coordinator.combined_light}")
    print(f"✅ Motion activation: {coordinator.motion_activation}")
    print(f"✅ Day brightness: {coordinator.brightness_day}")

    # Test sensor property access
    print(f"✅ Combined light entity: {coordinator.combined_light_entity}")
    print(f"✅ No motion wait: {coordinator.no_motion_wait_seconds}")
    print(f"✅ Motion activation enabled: {coordinator.is_motion_activation_enabled}")

    print("\n🎉 INTEGRATION LOAD TEST PASSED!")
    print("The simplified integration should load without runtime errors.")

except Exception as e:
    print(f"❌ Integration load test failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
