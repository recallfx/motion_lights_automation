"""Test ambient light sensor with lux sensor and hysteresis."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_EXTENDED_TIMEOUT,
    CONF_LIGHTS,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    DOMAIN,
    STATE_IDLE,
    STATE_MOTION_AUTO,
)
from custom_components.motion_lights_automation.motion_coordinator import (
    MotionLightsCoordinator,
)


async def test_binary_sensor_on_uses_dim_brightness(hass: HomeAssistant) -> None:
    """Test that binary sensor ON uses inactive brightness (dim mode)."""
    # Set up entities
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set("binary_sensor.ambient_light", "on")  # ON = low light

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Ambient Light",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_MOTION_ACTIVATION: True,
            CONF_AMBIENT_LIGHT_SENSOR: "binary_sensor.ambient_light",
            CONF_BRIGHTNESS_ACTIVE: 80,
            CONF_BRIGHTNESS_INACTIVE: 10,
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="test_entry_id",
        source="user",
        unique_id=None,
        discovery_keys={},
    )

    coordinator = MotionLightsCoordinator(hass, config_entry)
    await coordinator.async_setup_listeners()

    try:
        # Get context - should use dim brightness when sensor is ON
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is True
        assert context["is_dark_inside"] is True  # Legacy compatibility
    finally:
        coordinator.async_cleanup_listeners()


async def test_binary_sensor_off_uses_bright_brightness(hass: HomeAssistant) -> None:
    """Test that binary sensor OFF uses active brightness (bright mode)."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set(
        "binary_sensor.ambient_light", "off"
    )  # OFF = sufficient light

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Ambient Light",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_AMBIENT_LIGHT_SENSOR: "binary_sensor.ambient_light",
            CONF_BRIGHTNESS_ACTIVE: 80,
            CONF_BRIGHTNESS_INACTIVE: 10,
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="test_entry_id",
        source="user",
        unique_id=None,
        discovery_keys={},
    )

    coordinator = MotionLightsCoordinator(hass, config_entry)
    await coordinator.async_setup_listeners()

    try:
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is False
    finally:
        coordinator.async_cleanup_listeners()


async def test_lux_sensor_below_low_threshold_is_dim(hass: HomeAssistant) -> None:
    """Test lux sensor below LOW threshold (30) triggers dim mode."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    # Create lux sensor with unit_of_measurement
    hass.states.async_set(
        "sensor.illuminance",
        "20",  # Below LOW threshold (30)
        {"unit_of_measurement": "lx"},
    )

    config_entry = ConfigEntry(
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
        entry_id="test_entry_id",
        source="user",
        unique_id=None,
        discovery_keys={},
    )

    coordinator = MotionLightsCoordinator(hass, config_entry)
    await coordinator.async_setup_listeners()

    try:
        # First evaluation - 20 lux is below threshold (50), should be dim
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is True
        assert coordinator._brightness_mode_is_dim is True
    finally:
        coordinator.async_cleanup_listeners()


async def test_lux_sensor_above_high_threshold_is_bright(hass: HomeAssistant) -> None:
    """Test lux sensor above HIGH threshold (70) triggers bright mode."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set(
        "sensor.illuminance",
        "100",  # Above HIGH threshold (70)
        {"unit_of_measurement": "lx"},
    )

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Lux Sensor",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_AMBIENT_LIGHT_SENSOR: "sensor.illuminance",
            CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            CONF_BRIGHTNESS_ACTIVE: 80,
            CONF_BRIGHTNESS_INACTIVE: 10,
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="test_entry_id",
        source="user",
        unique_id=None,
        discovery_keys={},
    )

    coordinator = MotionLightsCoordinator(hass, config_entry)
    await coordinator.async_setup_listeners()

    try:
        # First evaluation - 100 lux is above threshold (50), should be bright
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is False
        assert coordinator._brightness_mode_is_dim is False
    finally:
        coordinator.async_cleanup_listeners()


async def test_lux_sensor_hysteresis_stays_dim_in_deadzone(hass: HomeAssistant) -> None:
    """Test hysteresis - once dim, stays dim until above HIGH threshold."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set(
        "sensor.illuminance",
        "20",  # Start dim
        {"unit_of_measurement": "lx"},
    )

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Lux Hysteresis",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_AMBIENT_LIGHT_SENSOR: "sensor.illuminance",
            CONF_AMBIENT_LIGHT_THRESHOLD: 50,  # LOW=30, HIGH=70
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="test_entry_id",
        source="user",
        unique_id=None,
        discovery_keys={},
    )

    coordinator = MotionLightsCoordinator(hass, config_entry)
    await coordinator.async_setup_listeners()

    try:
        # Start at 20 lux - should be dim
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is True

        # Rise to 50 lux (in deadzone) - should STAY dim
        hass.states.async_set(
            "sensor.illuminance",
            "50",
            {"unit_of_measurement": "lx"},
        )
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is True

        # Rise to 65 lux (still in deadzone) - should STAY dim
        hass.states.async_set(
            "sensor.illuminance",
            "65",
            {"unit_of_measurement": "lx"},
        )
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is True

        # Rise to 75 lux (above HIGH threshold) - NOW switch to bright
        hass.states.async_set(
            "sensor.illuminance",
            "75",
            {"unit_of_measurement": "lx"},
        )
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is False
    finally:
        coordinator.async_cleanup_listeners()


async def test_lux_sensor_hysteresis_stays_bright_in_deadzone(
    hass: HomeAssistant,
) -> None:
    """Test hysteresis - once bright, stays bright until below LOW threshold."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set(
        "sensor.illuminance",
        "100",  # Start bright
        {"unit_of_measurement": "lx"},
    )

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Lux Hysteresis",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_AMBIENT_LIGHT_SENSOR: "sensor.illuminance",
            CONF_AMBIENT_LIGHT_THRESHOLD: 50,  # LOW=30, HIGH=70
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="test_entry_id",
        source="user",
        unique_id=None,
        discovery_keys={},
    )

    coordinator = MotionLightsCoordinator(hass, config_entry)
    await coordinator.async_setup_listeners()

    try:
        # Start at 100 lux - should be bright
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is False

        # Drop to 50 lux (in deadzone) - should STAY bright
        hass.states.async_set(
            "sensor.illuminance",
            "50",
            {"unit_of_measurement": "lx"},
        )
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is False

        # Drop to 35 lux (still in deadzone) - should STAY bright
        hass.states.async_set(
            "sensor.illuminance",
            "35",
            {"unit_of_measurement": "lx"},
        )
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is False

        # Drop to 25 lux (below LOW threshold) - NOW switch to dim
        hass.states.async_set(
            "sensor.illuminance",
            "25",
            {"unit_of_measurement": "lx"},
        )
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is True
    finally:
        coordinator.async_cleanup_listeners()


async def test_lux_sensor_prevents_flickering_from_clouds(hass: HomeAssistant) -> None:
    """Test that brief lux changes (like clouds) don't cause mode switching."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set(
        "sensor.illuminance",
        "80",  # Start bright (above threshold)
        {"unit_of_measurement": "lx"},
    )

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Cloud Resistance",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_AMBIENT_LIGHT_SENSOR: "sensor.illuminance",
            CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="test_entry_id",
        source="user",
        unique_id=None,
        discovery_keys={},
    )

    coordinator = MotionLightsCoordinator(hass, config_entry)
    await coordinator.async_setup_listeners()

    try:
        # Start at 80 lux - bright mode
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is False

        # Cloud passes - drops to 45 lux (in deadzone)
        hass.states.async_set("sensor.illuminance", "45", {"unit_of_measurement": "lx"})
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is False  # STAYS bright

        # Cloud passes - back to 60 lux
        hass.states.async_set("sensor.illuminance", "60", {"unit_of_measurement": "lx"})
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is False  # Still bright

        # Another cloud - drops to 40 lux
        hass.states.async_set("sensor.illuminance", "40", {"unit_of_measurement": "lx"})
        context = coordinator._get_context()
        assert (
            context["use_dim_brightness"] is False
        )  # STILL bright (hysteresis working!)
    finally:
        coordinator.async_cleanup_listeners()


async def test_lux_sensor_with_motion_activation(hass: HomeAssistant) -> None:
    """Test lux sensor works correctly with motion activation."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set(
        "sensor.illuminance",
        "20",  # Low light - should use dim brightness
        {"unit_of_measurement": "lx"},
    )

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
        entry_id="test_entry_id",
        source="user",
        unique_id=None,
        discovery_keys={},
    )

    coordinator = MotionLightsCoordinator(hass, config_entry)
    await coordinator.async_setup_listeners()

    try:
        # Verify initial state
        assert coordinator.current_state == STATE_IDLE

        # Trigger motion - should activate with dim brightness (20 lux < 30)
        hass.states.async_set("binary_sensor.motion", "on")
        await hass.async_block_till_done()

        assert coordinator.current_state == STATE_MOTION_AUTO
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is True
    finally:
        coordinator.async_cleanup_listeners()


async def test_invalid_lux_value_falls_back_to_dim(hass: HomeAssistant) -> None:
    """Test that invalid lux values fall back to dim mode (safe default)."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set(
        "sensor.illuminance",
        "unknown",  # Invalid value
        {"unit_of_measurement": "lx"},
    )

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Invalid Lux",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_AMBIENT_LIGHT_SENSOR: "sensor.illuminance",
            CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="test_entry_id",
        source="user",
        unique_id=None,
        discovery_keys={},
    )

    coordinator = MotionLightsCoordinator(hass, config_entry)
    await coordinator.async_setup_listeners()

    try:
        # Should fall back to dim mode (safe default)
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is True
    finally:
        coordinator.async_cleanup_listeners()


async def test_custom_threshold_values(hass: HomeAssistant) -> None:
    """Test custom threshold values work correctly."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set(
        "sensor.illuminance",
        "50",
        {"unit_of_measurement": "lx"},
    )

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
        entry_id="test_entry_id",
        source="user",
        unique_id=None,
        discovery_keys={},
    )

    coordinator = MotionLightsCoordinator(hass, config_entry)
    await coordinator.async_setup_listeners()

    try:
        # 50 lux is below threshold (100), should be dim
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is True

        # Rise to 90 lux (in deadzone 80-120) - stays dim
        hass.states.async_set("sensor.illuminance", "90", {"unit_of_measurement": "lx"})
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is True

        # Rise to 125 lux (above 120) - switches to bright
        hass.states.async_set(
            "sensor.illuminance", "125", {"unit_of_measurement": "lx"}
        )
        context = coordinator._get_context()
        assert context["use_dim_brightness"] is False
    finally:
        coordinator.async_cleanup_listeners()
