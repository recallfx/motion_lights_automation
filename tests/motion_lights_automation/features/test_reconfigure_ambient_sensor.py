"""Test reconfiguration of ambient light sensor."""

from unittest.mock import patch

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_HOUSE_ACTIVE,
    CONF_LIGHTS,
    CONF_MOTION_ENTITY,
    CONF_OVERRIDE_SWITCH,
    DOMAIN,
)


async def test_reconfigure_remove_ambient_sensor(
    hass: HomeAssistant,
) -> None:
    """Test that removing ambient sensor during reconfiguration works."""
    # Mock the setup_entry to avoid actually setting up the integration
    with patch(
        "custom_components.motion_lights_automation.async_setup_entry",
        return_value=True,
    ):
        # Set up entities
        hass.states.async_set("binary_sensor.m1", "off")
        hass.states.async_set("light.ceiling1", "off")
        hass.states.async_set("sensor.ambient", "100")

        # Create initial entry WITH ambient sensor
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "Test Room",
                CONF_MOTION_ENTITY: ["binary_sensor.m1"],
                CONF_LIGHTS: ["light.ceiling1"],
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.ambient",  # Initially SET
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )

        entry_id = result["result"].entry_id
        entry = hass.config_entries.async_get_entry(entry_id)

        # Verify ambient sensor is in initial config
        assert CONF_AMBIENT_LIGHT_SENSOR in entry.data
        assert entry.data[CONF_AMBIENT_LIGHT_SENSOR] == "sensor.ambient"

        # Now reconfigure and REMOVE ambient sensor
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry_id},
        )

        # Don't include ambient sensor in reconfigure
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "Test Room",
                CONF_MOTION_ENTITY: ["binary_sensor.m1"],
                CONF_LIGHTS: ["light.ceiling1"],
                # CONF_AMBIENT_LIGHT_SENSOR is NOT provided - should be removed
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reconfigure_advanced"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"

        # Check the entry data after reconfiguration
        entry = hass.config_entries.async_get_entry(entry_id)

        # The ambient sensor should be removed or None
        if CONF_AMBIENT_LIGHT_SENSOR in entry.data:
            # If present, it should be None
            assert (
                entry.data[CONF_AMBIENT_LIGHT_SENSOR] is None
            ), f"Expected None but got {entry.data[CONF_AMBIENT_LIGHT_SENSOR]}"
        # Otherwise it's not in the dict at all, which is also fine


async def test_reconfigure_add_ambient_sensor(
    hass: HomeAssistant,
) -> None:
    """Test that adding ambient sensor during reconfiguration works."""
    # Mock the setup_entry to avoid actually setting up the integration
    with patch(
        "custom_components.motion_lights_automation.async_setup_entry",
        return_value=True,
    ):
        # Set up entities
        hass.states.async_set("binary_sensor.m1", "off")
        hass.states.async_set("light.ceiling1", "off")
        hass.states.async_set("sensor.ambient", "100")

        # Create initial entry WITHOUT ambient sensor
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "Test Room",
                CONF_MOTION_ENTITY: ["binary_sensor.m1"],
                CONF_LIGHTS: ["light.ceiling1"],
                # No ambient sensor
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )

        entry_id = result["result"].entry_id
        entry = hass.config_entries.async_get_entry(entry_id)

        # Verify no ambient sensor initially
        assert entry.data.get(CONF_AMBIENT_LIGHT_SENSOR) is None

        # Now reconfigure and ADD ambient sensor
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry_id},
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "Test Room",
                CONF_MOTION_ENTITY: ["binary_sensor.m1"],
                CONF_LIGHTS: ["light.ceiling1"],
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.ambient",  # Now ADD it
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reconfigure_advanced"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"

        # Check the entry data after reconfiguration
        entry = hass.config_entries.async_get_entry(entry_id)

        # The ambient sensor should now be present
        assert CONF_AMBIENT_LIGHT_SENSOR in entry.data
        assert entry.data[CONF_AMBIENT_LIGHT_SENSOR] == "sensor.ambient"


async def test_reconfigure_remove_all_optional_entities(
    hass: HomeAssistant,
) -> None:
    """Test that removing all optional entities during reconfiguration works."""
    # Mock the setup_entry to avoid actually setting up the integration
    with patch(
        "custom_components.motion_lights_automation.async_setup_entry",
        return_value=True,
    ):
        # Set up entities
        hass.states.async_set("binary_sensor.m1", "off")
        hass.states.async_set("light.ceiling1", "off")
        hass.states.async_set("sensor.ambient", "100")
        hass.states.async_set("switch.override", "off")
        hass.states.async_set("input_boolean.house_active", "on")

        # Create initial entry WITH all optional entities
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "Test Room",
                CONF_MOTION_ENTITY: ["binary_sensor.m1"],
                CONF_LIGHTS: ["light.ceiling1"],
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.ambient",
                CONF_OVERRIDE_SWITCH: "switch.override",
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )

        entry_id = result["result"].entry_id
        entry = hass.config_entries.async_get_entry(entry_id)

        # Verify all optional entities are in initial config
        assert entry.data[CONF_AMBIENT_LIGHT_SENSOR] == "sensor.ambient"
        assert entry.data[CONF_OVERRIDE_SWITCH] == "switch.override"
        assert entry.data[CONF_HOUSE_ACTIVE] == "input_boolean.house_active"

        # Now reconfigure and REMOVE all optional entities
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry_id},
        )

        # Don't include any optional entities
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_NAME: "Test Room",
                CONF_MOTION_ENTITY: ["binary_sensor.m1"],
                CONF_LIGHTS: ["light.ceiling1"],
                # No optional entities provided
            },
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reconfigure_advanced"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={},
        )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"

        # Check the entry data after reconfiguration
        entry = hass.config_entries.async_get_entry(entry_id)

        # All optional entities should be removed or None
        for field in [
            CONF_AMBIENT_LIGHT_SENSOR,
            CONF_OVERRIDE_SWITCH,
            CONF_HOUSE_ACTIVE,
        ]:
            if field in entry.data:
                assert (
                    entry.data[field] is None
                ), f"Expected {field} to be None but got {entry.data[field]}"
