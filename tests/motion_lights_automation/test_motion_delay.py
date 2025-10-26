"""Test motion delay feature for coordinating multiple instances."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.motion_lights_automation.const import (
    CONF_EXTENDED_TIMEOUT,
    CONF_LIGHTS,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_DELAY,
    CONF_MOTION_ENTITY,
    DOMAIN,
    STATE_IDLE,
    STATE_MOTION_AUTO,
)
from custom_components.motion_lights_automation.motion_coordinator import (
    MotionLightsCoordinator,
)


async def test_motion_delay_zero_activates_immediately(hass: HomeAssistant) -> None:
    """Test that delay=0 activates lights immediately (default behavior)."""
    # Set up entities
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Motion Lights",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_MOTION_ACTIVATION: True,
            CONF_MOTION_DELAY: 0,  # No delay
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

        # Trigger motion - should activate immediately
        hass.states.async_set("binary_sensor.motion", "on")
        await hass.async_block_till_done()

        # Should transition to MOTION_AUTO immediately
        assert coordinator.current_state == STATE_MOTION_AUTO
    finally:
        coordinator.async_cleanup_listeners()


async def test_motion_delay_activates_after_delay(hass: HomeAssistant) -> None:
    """Test that delay>0 waits before activating lights."""
    # Set up entities
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.test", "off")

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Motion Lights",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_MOTION_ACTIVATION: True,
            CONF_MOTION_DELAY: 5,  # 5 second delay
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

        # Trigger motion
        hass.states.async_set("binary_sensor.motion", "on")
        await hass.async_block_till_done()

        # Should still be in IDLE (delay timer running)
        assert coordinator.current_state == STATE_IDLE
        assert coordinator.timer_manager.has_active_timer("motion_delay")

        # Advance time by 4 seconds - still waiting
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=4))
        await hass.async_block_till_done()
        assert coordinator.current_state == STATE_IDLE

        # Advance time by 2 more seconds (total 6s > 5s delay) - should activate now
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=6))
        await hass.async_block_till_done()

        # Should now transition to MOTION_AUTO
        assert coordinator.current_state == STATE_MOTION_AUTO
        assert not coordinator.timer_manager.has_active_timer("motion_delay")
    finally:
        coordinator.async_cleanup_listeners()


async def test_motion_delay_multiple_instances_stagger(hass: HomeAssistant) -> None:
    """Test that multiple instances with different delays create staggered activation."""
    # Set up shared motion sensor
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.kitchen", "off")
    hass.states.async_set("light.hallway", "off")
    hass.states.async_set("light.bedroom", "off")

    # Instance 1: Kitchen with 0s delay
    config_kitchen = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Kitchen Lights",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.kitchen"],
            CONF_MOTION_DELAY: 0,
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="kitchen_id",
        source="user",
        unique_id="kitchen",
        discovery_keys={},
    )

    # Instance 2: Hallway with 2s delay
    config_hallway = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Hallway Lights",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.hallway"],
            CONF_MOTION_DELAY: 2,
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="hallway_id",
        source="user",
        unique_id="hallway",
        discovery_keys={},
    )

    # Instance 3: Bedroom with 4s delay
    config_bedroom = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Bedroom Lights",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.bedroom"],
            CONF_MOTION_DELAY: 4,
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="bedroom_id",
        source="user",
        unique_id="bedroom",
        discovery_keys={},
    )

    coord_kitchen = MotionLightsCoordinator(hass, config_kitchen)
    coord_hallway = MotionLightsCoordinator(hass, config_hallway)
    coord_bedroom = MotionLightsCoordinator(hass, config_bedroom)

    await coord_kitchen.async_setup_listeners()
    await coord_hallway.async_setup_listeners()
    await coord_bedroom.async_setup_listeners()

    try:
        # All start in IDLE
        assert coord_kitchen.current_state == STATE_IDLE
        assert coord_hallway.current_state == STATE_IDLE
        assert coord_bedroom.current_state == STATE_IDLE

        # Trigger motion
        hass.states.async_set("binary_sensor.motion", "on")
        await hass.async_block_till_done()

        # Kitchen activates immediately (0s delay)
        assert coord_kitchen.current_state == STATE_MOTION_AUTO
        assert coord_hallway.current_state == STATE_IDLE
        assert coord_bedroom.current_state == STATE_IDLE

        # Advance 2 seconds - hallway activates
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
        await hass.async_block_till_done()
        assert coord_kitchen.current_state == STATE_MOTION_AUTO
        assert coord_hallway.current_state == STATE_MOTION_AUTO
        assert coord_bedroom.current_state == STATE_IDLE

        # Advance to 4 seconds total - bedroom activates
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=4))
        await hass.async_block_till_done()
        assert coord_kitchen.current_state == STATE_MOTION_AUTO
        assert coord_hallway.current_state == STATE_MOTION_AUTO
        assert coord_bedroom.current_state == STATE_MOTION_AUTO
    finally:
        coord_kitchen.async_cleanup_listeners()
        coord_hallway.async_cleanup_listeners()
        coord_bedroom.async_cleanup_listeners()
