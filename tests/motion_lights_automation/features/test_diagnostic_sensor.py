"""Test diagnostic sensor functionality."""

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_EXTENDED_TIMEOUT,
    CONF_HOUSE_ACTIVE,
    CONF_LIGHTS,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    DOMAIN,
)


async def test_diagnostic_sensor_created(hass: HomeAssistant) -> None:
    """Test that diagnostic sensor is created."""
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
        entry_id="test_diagnostic",
    )

    # Set up mock entities
    hass.states.async_set("binary_sensor.motion", STATE_OFF)
    hass.states.async_set("light.test", STATE_OFF)

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Check that diagnostic sensor exists
    # Entity ID is based on config entry title
    diagnostic_sensor_entity_id = "sensor.mock_title_lighting_automation"
    diagnostic_state = hass.states.get(diagnostic_sensor_entity_id)
    assert diagnostic_state is not None
    # State is now the last event message - after initialization it should show restart message
    assert "Integration restarted" in diagnostic_state.state

    # Cleanup
    coordinator = config_entry.runtime_data
    coordinator.async_cleanup_listeners()


async def test_diagnostic_sensor_tracks_events(hass: HomeAssistant) -> None:
    """Test that diagnostic sensor tracks events."""
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
        entry_id="test_diagnostic_events",
    )

    # Set up mock entities
    hass.states.async_set("binary_sensor.motion", STATE_OFF)
    hass.states.async_set("light.test", STATE_OFF)

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Get diagnostic sensor
    diagnostic_sensor_entity_id = "sensor.mock_title_lighting_automation"
    diagnostic_state = hass.states.get(diagnostic_sensor_entity_id)
    assert diagnostic_state is not None

    # Trigger motion
    hass.states.async_set("binary_sensor.motion", STATE_ON)
    await hass.async_block_till_done()

    # Check that event was logged
    diagnostic_state = hass.states.get(diagnostic_sensor_entity_id)
    event_log = diagnostic_state.attributes.get("event_log", [])
    assert len(event_log) > 0

    # Event log should contain motion-related event
    # The format may vary, so check for common patterns
    assert len(event_log) > 0, "Event log should not be empty after motion"
    log_text = " ".join(event_log).lower()
    assert "motion" in log_text, f"Expected 'motion' in event log: {event_log}"

    # Cleanup
    coordinator = config_entry.runtime_data
    coordinator.async_cleanup_listeners()


async def test_diagnostic_sensor_tracks_transitions(hass: HomeAssistant) -> None:
    """Test that diagnostic sensor tracks state transitions."""
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
        entry_id="test_diagnostic_transitions",
    )

    # Set up mock entities
    hass.states.async_set("binary_sensor.motion", STATE_OFF)
    hass.states.async_set("light.test", STATE_OFF)

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Get diagnostic sensor
    diagnostic_sensor_entity_id = "sensor.mock_title_lighting_automation"

    # Trigger motion to cause state transition
    hass.states.async_set("binary_sensor.motion", STATE_ON)
    await hass.async_block_till_done()

    diagnostic_state = hass.states.get(diagnostic_sensor_entity_id)
    assert diagnostic_state is not None

    # Check last transition info
    last_transition_reason = diagnostic_state.attributes.get("last_transition_reason")
    assert last_transition_reason is not None
    assert "motion_on" in last_transition_reason

    last_transition_time = diagnostic_state.attributes.get("last_transition_time")
    assert last_transition_time is not None

    # Cleanup
    coordinator = config_entry.runtime_data
    coordinator.async_cleanup_listeners()


async def test_diagnostic_sensor_shows_conditions(hass: HomeAssistant) -> None:
    """Test that diagnostic sensor shows current conditions."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_HOUSE_ACTIVE: ["switch.house_active"],
            CONF_AMBIENT_LIGHT_SENSOR: ["binary_sensor.ambient"],
            CONF_NO_MOTION_WAIT: 300,
            CONF_EXTENDED_TIMEOUT: 1200,
            CONF_BRIGHTNESS_ACTIVE: 100,
            CONF_BRIGHTNESS_INACTIVE: 30,
            CONF_MOTION_ACTIVATION: True,
        },
        entry_id="test_diagnostic_conditions",
    )

    # Set up mock entities
    hass.states.async_set("binary_sensor.motion", STATE_ON)
    hass.states.async_set("light.test", STATE_OFF)
    hass.states.async_set("switch.house_active", STATE_ON)
    hass.states.async_set("binary_sensor.ambient", STATE_ON)

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Get diagnostic sensor
    diagnostic_sensor_entity_id = "sensor.mock_title_lighting_automation"
    diagnostic_state = hass.states.get(diagnostic_sensor_entity_id)
    assert diagnostic_state is not None

    # Check conditions are tracked
    motion_active = diagnostic_state.attributes.get("motion_active")
    is_dark_inside = diagnostic_state.attributes.get("is_dark_inside")
    is_house_active = diagnostic_state.attributes.get("is_house_active")
    motion_activation_enabled = diagnostic_state.attributes.get(
        "motion_activation_enabled"
    )

    assert motion_active is True
    assert is_dark_inside is True  # binary sensor ON means dark
    assert is_house_active is True
    assert motion_activation_enabled is True

    # Cleanup
    coordinator = config_entry.runtime_data
    coordinator.async_cleanup_listeners()
