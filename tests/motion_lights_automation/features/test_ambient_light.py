"""Comprehensive tests for ambient light sensor functionality.

Tests cover:
- Binary sensor behavior (ON = dark, OFF = bright)
- Lux sensor behavior with hysteresis
- State change reactions (becoming dark/bright)
- Activation prevention when bright
- House active integration
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_EXTENDED_TIMEOUT,
    CONF_HOUSE_ACTIVE,
    CONF_LIGHTS,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    DOMAIN,
)
from custom_components.motion_lights_automation.state_machine import (
    STATE_IDLE,
    STATE_MOTION_AUTO,
)
from custom_components.motion_lights_automation.light_controller import (
    TimeOfDayBrightnessStrategy,
)
from custom_components.motion_lights_automation.motion_coordinator import (
    MotionLightsCoordinator,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def basic_ambient_entry(hass):
    """Create a config entry with binary ambient sensor."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Ambient Light",
        data={
            CONF_NAME: "Test Room",
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_AMBIENT_LIGHT_SENSOR: "binary_sensor.ambient_light",
            CONF_MOTION_ACTIVATION: True,
            CONF_BRIGHTNESS_ACTIVE: 80,
            CONF_BRIGHTNESS_INACTIVE: 10,
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="test_ambient_entry",
        source="user",
        unique_id="test_ambient_unique",
        discovery_keys={},
    )


@pytest.fixture
def lux_sensor_entry(hass):
    """Create a config entry with lux sensor."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Lux Sensor",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_AMBIENT_LIGHT_SENSOR: "sensor.illuminance",
            CONF_AMBIENT_LIGHT_THRESHOLD: 50,  # LOW=30, HIGH=70
            CONF_BRIGHTNESS_ACTIVE: 80,
            CONF_BRIGHTNESS_INACTIVE: 10,
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="test_lux_entry",
        source="user",
        unique_id="test_lux_unique",
        discovery_keys={},
    )


# =============================================================================
# Binary Sensor Tests
# =============================================================================


class TestBinarySensorBehavior:
    """Tests for binary ambient light sensor behavior."""

    async def test_binary_sensor_on_indicates_dark(
        self, hass: HomeAssistant, basic_ambient_entry
    ):
        """Test that binary sensor ON indicates dark (allows light activation)."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")
        hass.states.async_set("binary_sensor.ambient_light", "on")

        coordinator = MotionLightsCoordinator(hass, basic_ambient_entry)
        await coordinator.async_setup_listeners()

        try:
            context = coordinator._get_context()
            assert context["is_dark_inside"] is True

            strategy = TimeOfDayBrightnessStrategy(
                active_brightness=80, inactive_brightness=10
            )
            brightness = strategy.get_brightness(context)
            assert brightness == 80
        finally:
            coordinator.async_cleanup_listeners()

    async def test_binary_sensor_off_indicates_bright(
        self, hass: HomeAssistant, basic_ambient_entry
    ):
        """Test that binary sensor OFF indicates bright (prevents activation)."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")
        hass.states.async_set("binary_sensor.ambient_light", "off")

        coordinator = MotionLightsCoordinator(hass, basic_ambient_entry)
        await coordinator.async_setup_listeners()

        try:
            context = coordinator._get_context()
            assert context["is_dark_inside"] is False

            strategy = TimeOfDayBrightnessStrategy(
                active_brightness=80, inactive_brightness=10
            )
            brightness = strategy.get_brightness(context)
            assert brightness == 0
        finally:
            coordinator.async_cleanup_listeners()

    async def test_binary_sensor_off_prevents_light_activation(
        self, hass: HomeAssistant, basic_ambient_entry
    ):
        """Test that motion with bright ambient doesn't effectively turn on lights."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")
        hass.states.async_set("binary_sensor.ambient_light", "off")

        coordinator = MotionLightsCoordinator(hass, basic_ambient_entry)
        await coordinator.async_setup_listeners()

        try:
            assert coordinator.current_state == STATE_IDLE

            # Trigger motion
            hass.states.async_set("binary_sensor.motion", "on")
            await hass.async_block_till_done()

            # State transitions but brightness is 0
            assert coordinator.current_state == STATE_MOTION_AUTO
            context = coordinator._get_context()
            brightness = (
                coordinator.light_controller._brightness_strategy.get_brightness(
                    context
                )
            )
            assert brightness == 0
        finally:
            coordinator.async_cleanup_listeners()


# =============================================================================
# Lux Sensor Tests
# =============================================================================


class TestLuxSensorBehavior:
    """Tests for lux sensor with hysteresis."""

    async def test_lux_below_low_threshold_is_dark(
        self, hass: HomeAssistant, lux_sensor_entry
    ):
        """Test lux below LOW threshold (30) indicates dark."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")
        hass.states.async_set("sensor.illuminance", "20", {"unit_of_measurement": "lx"})

        coordinator = MotionLightsCoordinator(hass, lux_sensor_entry)
        await coordinator.async_setup_listeners()

        try:
            context = coordinator._get_context()
            assert context["is_dark_inside"] is True
            assert coordinator._brightness_mode_is_dim is True
        finally:
            coordinator.async_cleanup_listeners()

    async def test_lux_above_high_threshold_is_bright(
        self, hass: HomeAssistant, lux_sensor_entry
    ):
        """Test lux above HIGH threshold (70) indicates bright."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")
        hass.states.async_set(
            "sensor.illuminance", "100", {"unit_of_measurement": "lx"}
        )

        coordinator = MotionLightsCoordinator(hass, lux_sensor_entry)
        await coordinator.async_setup_listeners()

        try:
            context = coordinator._get_context()
            assert context["is_dark_inside"] is False
            assert coordinator._brightness_mode_is_dim is False
        finally:
            coordinator.async_cleanup_listeners()

    async def test_hysteresis_stays_dim_in_deadzone(
        self, hass: HomeAssistant, lux_sensor_entry
    ):
        """Test hysteresis - once dim, stays dim until above HIGH threshold."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")
        hass.states.async_set("sensor.illuminance", "20", {"unit_of_measurement": "lx"})

        coordinator = MotionLightsCoordinator(hass, lux_sensor_entry)
        await coordinator.async_setup_listeners()

        try:
            # Start dim
            context = coordinator._get_context()
            assert context["is_dark_inside"] is True

            # Rise to 50 lux (deadzone) - stays dim
            hass.states.async_set(
                "sensor.illuminance", "50", {"unit_of_measurement": "lx"}
            )
            context = coordinator._get_context()
            assert context["is_dark_inside"] is True

            # Rise to 65 lux (still deadzone) - stays dim
            hass.states.async_set(
                "sensor.illuminance", "65", {"unit_of_measurement": "lx"}
            )
            context = coordinator._get_context()
            assert context["is_dark_inside"] is True

            # Rise to 75 lux (above HIGH) - switches to bright
            hass.states.async_set(
                "sensor.illuminance", "75", {"unit_of_measurement": "lx"}
            )
            context = coordinator._get_context()
            assert context["is_dark_inside"] is False
        finally:
            coordinator.async_cleanup_listeners()

    async def test_hysteresis_stays_bright_in_deadzone(
        self, hass: HomeAssistant, lux_sensor_entry
    ):
        """Test hysteresis - once bright, stays bright until below LOW threshold."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")
        hass.states.async_set(
            "sensor.illuminance", "100", {"unit_of_measurement": "lx"}
        )

        coordinator = MotionLightsCoordinator(hass, lux_sensor_entry)
        await coordinator.async_setup_listeners()

        try:
            # Start bright
            context = coordinator._get_context()
            assert context["is_dark_inside"] is False

            # Drop to 50 lux (deadzone) - stays bright
            hass.states.async_set(
                "sensor.illuminance", "50", {"unit_of_measurement": "lx"}
            )
            context = coordinator._get_context()
            assert context["is_dark_inside"] is False

            # Drop to 35 lux (still deadzone) - stays bright
            hass.states.async_set(
                "sensor.illuminance", "35", {"unit_of_measurement": "lx"}
            )
            context = coordinator._get_context()
            assert context["is_dark_inside"] is False

            # Drop to 25 lux (below LOW) - switches to dim
            hass.states.async_set(
                "sensor.illuminance", "25", {"unit_of_measurement": "lx"}
            )
            context = coordinator._get_context()
            assert context["is_dark_inside"] is True
        finally:
            coordinator.async_cleanup_listeners()

    async def test_hysteresis_prevents_cloud_flickering(
        self, hass: HomeAssistant, lux_sensor_entry
    ):
        """Test that brief lux changes (like clouds) don't cause mode switching."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")
        hass.states.async_set("sensor.illuminance", "80", {"unit_of_measurement": "lx"})

        coordinator = MotionLightsCoordinator(hass, lux_sensor_entry)
        await coordinator.async_setup_listeners()

        try:
            # Start bright
            context = coordinator._get_context()
            assert context["is_dark_inside"] is False

            # Cloud passes - drops to 45 lux (deadzone)
            hass.states.async_set(
                "sensor.illuminance", "45", {"unit_of_measurement": "lx"}
            )
            context = coordinator._get_context()
            assert context["is_dark_inside"] is False  # Stays bright

            # Cloud passes - back to 60 lux
            hass.states.async_set(
                "sensor.illuminance", "60", {"unit_of_measurement": "lx"}
            )
            context = coordinator._get_context()
            assert context["is_dark_inside"] is False  # Still bright

            # Another cloud - drops to 40 lux
            hass.states.async_set(
                "sensor.illuminance", "40", {"unit_of_measurement": "lx"}
            )
            context = coordinator._get_context()
            assert context["is_dark_inside"] is False  # Still bright
        finally:
            coordinator.async_cleanup_listeners()

    async def test_invalid_lux_value_falls_back_to_dim(
        self, hass: HomeAssistant, lux_sensor_entry
    ):
        """Test that invalid lux values fall back to dim mode."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")
        hass.states.async_set(
            "sensor.illuminance", "unknown", {"unit_of_measurement": "lx"}
        )

        coordinator = MotionLightsCoordinator(hass, lux_sensor_entry)
        await coordinator.async_setup_listeners()

        try:
            context = coordinator._get_context()
            assert context["is_dark_inside"] is True
        finally:
            coordinator.async_cleanup_listeners()

    async def test_custom_threshold_values(self, hass: HomeAssistant):
        """Test custom threshold values work correctly."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")
        hass.states.async_set("sensor.illuminance", "50", {"unit_of_measurement": "lx"})

        config_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Test Custom Threshold",
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.test"],
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.illuminance",
                CONF_AMBIENT_LIGHT_THRESHOLD: 100,  # LOW=80, HIGH=120
                CONF_EXTENDED_TIMEOUT: 1200,
            },
            options={},
            entry_id="test_custom_threshold",
            source="user",
            unique_id=None,
            discovery_keys={},
        )

        coordinator = MotionLightsCoordinator(hass, config_entry)
        await coordinator.async_setup_listeners()

        try:
            # 50 lux below threshold (100) - dim
            context = coordinator._get_context()
            assert context["is_dark_inside"] is True

            # 90 lux (deadzone 80-120) - stays dim
            hass.states.async_set(
                "sensor.illuminance", "90", {"unit_of_measurement": "lx"}
            )
            context = coordinator._get_context()
            assert context["is_dark_inside"] is True

            # 125 lux (above 120) - switches to bright
            hass.states.async_set(
                "sensor.illuminance", "125", {"unit_of_measurement": "lx"}
            )
            context = coordinator._get_context()
            assert context["is_dark_inside"] is False
        finally:
            coordinator.async_cleanup_listeners()


# =============================================================================
# State Change Reaction Tests
# =============================================================================


class TestAmbientStateChanges:
    """Tests for reactions to ambient light state changes."""

    async def test_becoming_dark_with_motion_turns_on_lights(
        self, hass: HomeAssistant, basic_ambient_entry
    ):
        """Test that becoming dark with active motion turns on lights."""
        hass.states.async_set("binary_sensor.motion", STATE_ON)
        hass.states.async_set("light.test", STATE_OFF)
        hass.states.async_set("binary_sensor.ambient_light", STATE_OFF)  # Bright

        coordinator = MotionLightsCoordinator(hass, basic_ambient_entry)
        await coordinator.async_setup_listeners()

        assert coordinator.state_machine.current_state == "idle"

        # Become dark - should activate lights
        hass.states.async_set("binary_sensor.ambient_light", STATE_ON)
        await hass.async_block_till_done()

        assert coordinator.state_machine.current_state == "motion-auto"
        coordinator.async_cleanup_listeners()

    async def test_becoming_bright_turns_off_auto_lights(
        self, hass: HomeAssistant, basic_ambient_entry
    ):
        """Test that becoming bright turns off auto-controlled lights."""
        hass.states.async_set("binary_sensor.motion", STATE_OFF)
        hass.states.async_set("light.test", STATE_OFF)
        hass.states.async_set("binary_sensor.ambient_light", STATE_ON)  # Dark

        coordinator = MotionLightsCoordinator(hass, basic_ambient_entry)
        await coordinator.async_setup_listeners()

        # Turn on motion
        hass.states.async_set("binary_sensor.motion", STATE_ON)
        await hass.async_block_till_done()
        assert coordinator.state_machine.current_state == "motion-auto"

        # Become bright - should turn off lights
        with patch.object(
            coordinator.light_controller, "turn_off_lights", new_callable=AsyncMock
        ) as mock_turn_off:
            hass.states.async_set("binary_sensor.ambient_light", STATE_OFF)
            await hass.async_block_till_done()
            mock_turn_off.assert_called_once()

        coordinator.async_cleanup_listeners()

    async def test_becoming_bright_in_manual_state_doesnt_force_off(
        self, hass: HomeAssistant, basic_ambient_entry
    ):
        """Test that becoming bright in MANUAL state doesn't force lights off."""
        hass.states.async_set("binary_sensor.motion", STATE_OFF)
        hass.states.async_set("light.test", STATE_ON)
        hass.states.async_set("binary_sensor.ambient_light", STATE_ON)

        coordinator = MotionLightsCoordinator(hass, basic_ambient_entry)
        await coordinator.async_setup_listeners()

        coordinator.state_machine.force_state("manual")

        with patch.object(
            coordinator.light_controller, "turn_off_lights", new_callable=AsyncMock
        ) as mock_turn_off:
            hass.states.async_set("binary_sensor.ambient_light", STATE_OFF)
            await hass.async_block_till_done()
            mock_turn_off.assert_not_called()

        assert coordinator.state_machine.current_state == "manual"
        coordinator.async_cleanup_listeners()


# =============================================================================
# House Active Integration Tests
# =============================================================================


class TestHouseActiveIntegration:
    """Tests for house active switch integration with ambient light."""

    async def test_house_active_changes_adjusts_brightness(self, hass: HomeAssistant):
        """Test that house active state change adjusts brightness."""
        entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Test House Active",
            data={
                CONF_NAME: "Test Room",
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.test"],
                CONF_AMBIENT_LIGHT_SENSOR: "binary_sensor.ambient",
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
                CONF_MOTION_ACTIVATION: True,
            },
            options={},
            entry_id="test_house_active",
            source="user",
            unique_id="test_house_active_unique",
            discovery_keys={},
        )

        hass.states.async_set("binary_sensor.motion", STATE_OFF)
        hass.states.async_set("light.test", STATE_OFF)
        hass.states.async_set("binary_sensor.ambient", STATE_ON)  # Dark
        hass.states.async_set("input_boolean.house_active", STATE_OFF)

        coordinator = MotionLightsCoordinator(hass, entry)
        await coordinator.async_setup_listeners()

        # Turn on motion
        hass.states.async_set("binary_sensor.motion", STATE_ON)
        await hass.async_block_till_done()
        assert coordinator.state_machine.current_state == "motion-auto"

        # Simulate lights on
        hass.states.async_set("light.test", STATE_ON, {"brightness": 26})
        await hass.async_block_till_done()

        # Activate house - should adjust brightness
        with patch.object(
            coordinator.light_controller, "turn_on_auto_lights", new_callable=AsyncMock
        ) as mock_turn_on:
            hass.states.async_set("input_boolean.house_active", STATE_ON)
            await hass.async_block_till_done()
            mock_turn_on.assert_called_once()

        coordinator.async_cleanup_listeners()


# =============================================================================
# No Ambient Sensor Tests
# =============================================================================


class TestNoAmbientSensor:
    """Tests for behavior when no ambient sensor is configured."""

    async def test_no_ambient_sensor_defaults_to_dark(self, hass: HomeAssistant):
        """Test that without ambient sensor, defaults to dark (allows activation)."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")

        config_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Test No Ambient",
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.test"],
                CONF_BRIGHTNESS_ACTIVE: 80,
                CONF_BRIGHTNESS_INACTIVE: 10,
                CONF_EXTENDED_TIMEOUT: 1200,
            },
            options={},
            entry_id="test_no_ambient",
            source="user",
            unique_id=None,
            discovery_keys={},
        )

        coordinator = MotionLightsCoordinator(hass, config_entry)
        await coordinator.async_setup_listeners()

        try:
            context = coordinator._get_context()
            assert context["is_dark_inside"] is True

            strategy = TimeOfDayBrightnessStrategy(
                active_brightness=80, inactive_brightness=10
            )
            brightness = strategy.get_brightness(context)
            assert brightness == 80
        finally:
            coordinator.async_cleanup_listeners()


# =============================================================================
# Motion Integration Tests
# =============================================================================


class TestLuxSensorWithMotion:
    """Tests for lux sensor integration with motion activation."""

    async def test_lux_sensor_with_motion_activation(self, hass: HomeAssistant):
        """Test lux sensor works correctly with motion activation."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")
        hass.states.async_set("sensor.illuminance", "20", {"unit_of_measurement": "lx"})

        config_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Test Lux with Motion",
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.test"],
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.illuminance",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
                CONF_MOTION_ACTIVATION: True,
                CONF_EXTENDED_TIMEOUT: 1200,
            },
            options={},
            entry_id="test_lux_motion",
            source="user",
            unique_id="test_lux_motion_unique",
            discovery_keys={},
        )

        coordinator = MotionLightsCoordinator(hass, config_entry)
        await coordinator.async_setup_listeners()

        try:
            assert coordinator.current_state == STATE_IDLE

            # Trigger motion
            hass.states.async_set("binary_sensor.motion", "on")
            await hass.async_block_till_done()

            assert coordinator.current_state == STATE_MOTION_AUTO
            context = coordinator._get_context()
            assert context["is_dark_inside"] is True
        finally:
            coordinator.async_cleanup_listeners()
