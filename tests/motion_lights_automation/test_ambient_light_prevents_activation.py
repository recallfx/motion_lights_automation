"""Test that ambient light sensor prevents light activation when bright."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
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


async def test_binary_sensor_off_prevents_light_activation(hass: HomeAssistant) -> None:
    """Test that when binary ambient sensor is OFF (bright), lights don't turn on."""
    # Set up entities
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set("binary_sensor.ambient_light", "off")  # OFF = bright outside

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Binary Ambient Prevents Activation",
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
        # Verify initial state
        assert coordinator.current_state == STATE_IDLE

        # Get context - should indicate bright mode
        context = coordinator._get_context()
        assert context["is_dark_inside"] is False

        # Verify brightness strategy returns 0 when bright
        from custom_components.motion_lights_automation.light_controller import (
            TimeOfDayBrightnessStrategy,
        )

        strategy = TimeOfDayBrightnessStrategy(
            active_brightness=80, inactive_brightness=10
        )
        brightness = strategy.get_brightness(context)
        assert brightness == 0, "Should return 0 brightness when bright outside"

        # Trigger motion
        hass.states.async_set("binary_sensor.motion", "on")
        await hass.async_block_till_done()

        # Should transition to motion-auto state (motion was detected)
        assert coordinator.current_state == STATE_MOTION_AUTO

        # But coordinator should have attempted to turn on lights with brightness=0
        # which means no lights actually turn on
        context = coordinator._get_context()
        brightness = coordinator.light_controller._brightness_strategy.get_brightness(
            context
        )
        assert brightness == 0, "Brightness should be 0 when ambient sensor is OFF"

    finally:
        coordinator.async_cleanup_listeners()


async def test_binary_sensor_on_allows_light_activation(hass: HomeAssistant) -> None:
    """Test that when binary ambient sensor is ON (dark), lights turn on normally."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set("binary_sensor.ambient_light", "on")  # ON = dark, low light

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Binary Ambient Allows Activation",
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
        # Get context - should indicate dim mode
        context = coordinator._get_context()
        assert context["is_dark_inside"] is True

        # Verify brightness strategy returns active brightness when dark
        from custom_components.motion_lights_automation.light_controller import (
            TimeOfDayBrightnessStrategy,
        )

        strategy = TimeOfDayBrightnessStrategy(
            active_brightness=80, inactive_brightness=10
        )
        brightness = strategy.get_brightness(context)
        assert brightness == 80, "Should return active brightness when dark"

    finally:
        coordinator.async_cleanup_listeners()


async def test_lux_below_threshold_allows_activation(hass: HomeAssistant) -> None:
    """Test that lux sensor below threshold allows lights to turn on."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set(
        "sensor.illuminance",
        "20",  # Below LOW threshold (30)
        {"unit_of_measurement": "lx"},
    )

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Lux Allows Activation",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_AMBIENT_LIGHT_SENSOR: "sensor.illuminance",
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
        assert context["is_dark_inside"] is True

        # Brightness should be active level when dark
        from custom_components.motion_lights_automation.light_controller import (
            TimeOfDayBrightnessStrategy,
        )

        strategy = TimeOfDayBrightnessStrategy(
            active_brightness=80, inactive_brightness=10
        )
        brightness = strategy.get_brightness(context)
        assert brightness == 80, "Should return active brightness when lux is low"

    finally:
        coordinator.async_cleanup_listeners()


async def test_lux_above_threshold_prevents_activation(hass: HomeAssistant) -> None:
    """Test that lux sensor above HIGH threshold prevents lights from turning on."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")
    hass.states.async_set(
        "sensor.illuminance",
        "100",  # Above HIGH threshold (70) for default 50 setting
        {"unit_of_measurement": "lx"},
    )

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Lux Prevents Activation",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_AMBIENT_LIGHT_SENSOR: "sensor.illuminance",
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
        assert context["is_dark_inside"] is False

        # Brightness should be 0 when bright outside
        from custom_components.motion_lights_automation.light_controller import (
            TimeOfDayBrightnessStrategy,
        )

        strategy = TimeOfDayBrightnessStrategy(
            active_brightness=80, inactive_brightness=10
        )
        brightness = strategy.get_brightness(context)
        assert brightness == 0, "Should return 0 brightness when lux is high (bright)"

    finally:
        coordinator.async_cleanup_listeners()


async def test_no_ambient_sensor_allows_activation(hass: HomeAssistant) -> None:
    """Test that without ambient sensor, lights activate normally."""
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test No Ambient Sensor",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            # No ambient light sensor configured
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
        # Without ambient sensor, defaults to dim mode (is_dark_inside=True)
        assert context["is_dark_inside"] is True

        # Should return active brightness
        from custom_components.motion_lights_automation.light_controller import (
            TimeOfDayBrightnessStrategy,
        )

        strategy = TimeOfDayBrightnessStrategy(
            active_brightness=80, inactive_brightness=10
        )
        brightness = strategy.get_brightness(context)
        assert (
            brightness == 80
        ), "Should return active brightness when no ambient sensor"

    finally:
        coordinator.async_cleanup_listeners()
