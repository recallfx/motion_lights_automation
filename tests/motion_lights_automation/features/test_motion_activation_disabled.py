"""Test motion_activation=False behavior - motion should reset timers but not turn on lights."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.motion_lights_automation.const import (
    CONF_EXTENDED_TIMEOUT,
    CONF_LIGHTS,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    DOMAIN,
)
from custom_components.motion_lights_automation.state_machine import (
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_MOTION_MANUAL,
)
from custom_components.motion_lights_automation.motion_coordinator import (
    MotionLightsCoordinator,
)
from custom_components.motion_lights_automation.timer_manager import TimerType


@pytest.fixture
def mock_config_data_motion_disabled():
    """Return config with motion_activation disabled."""
    return {
        CONF_MOTION_ENTITY: ["binary_sensor.motion"],
        CONF_LIGHTS: ["light.background"],
        CONF_MOTION_ACTIVATION: False,  # Motion activation disabled
        CONF_EXTENDED_TIMEOUT: 1200,  # 20 minutes
    }


async def test_motion_activation_disabled_prevents_auto_light_on(
    hass: HomeAssistant,
) -> None:
    """Test that when motion_activation is False, motion doesn't turn on lights."""
    # Set up entities
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.background", "off")

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Motion Lights",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.background"],
            CONF_MOTION_ACTIVATION: False,
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
        # Verify initial state is IDLE
        assert coordinator.current_state == STATE_IDLE

        # Trigger motion - should NOT turn on lights
        hass.states.async_set("binary_sensor.motion", "on")
        await hass.async_block_till_done()

        # State should still be IDLE and lights should still be off
        assert coordinator.current_state == STATE_IDLE
        assert hass.states.get("light.background").state == "off"
    finally:
        # Clean up
        coordinator.async_cleanup_listeners()


async def test_motion_activation_disabled_resets_timer_in_manual_state(
    hass: HomeAssistant,
) -> None:
    """Test that motion transitions to motion-adjusted when lights are manually on and motion_activation is False.

    When motion_activation is disabled, state transitions still happen normally.
    Only light activation from idle/manual-off states is blocked.
    """
    # Set up entities
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.background", "off")

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Motion Lights",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.background"],
            CONF_MOTION_ACTIVATION: False,
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
        # Mock startup time to simulate grace period expiry (beyond 180s)
        coordinator._startup_time = dt_util.now() - timedelta(seconds=200)

        # Manually turn on light (simulate user action)
        with patch.object(
            coordinator.light_controller, "is_integration_context", return_value=False
        ):
            hass.states.async_set(
                "light.background", "on", attributes={"brightness": 255}
            )
            await hass.async_block_till_done()

        # Should be in MANUAL state with extended timer running
        assert coordinator.current_state == STATE_MANUAL
        assert coordinator.timer_manager.has_active_timer("extended")

        # Wait a bit
        await hass.async_block_till_done()

        # Now trigger motion - should transition to MOTION_MANUAL and cancel timer
        hass.states.async_set("binary_sensor.motion", "on")
        await hass.async_block_till_done()

        # Should be in MOTION_MANUAL state (motion keeps lights on, no timer)
        assert coordinator.current_state == STATE_MOTION_MANUAL

        # Timer should be cancelled (motion keeps lights on)
        assert not coordinator.timer_manager.has_active_timer("extended")
    finally:
        # Clean up
        coordinator.async_cleanup_listeners()


async def test_motion_keeps_resetting_timer_preventing_shutoff(
    hass: HomeAssistant,
) -> None:
    """Test that continuous motion prevents lights from turning off by staying in motion-adjusted state.

    When motion is active, the system stays in MOTION_MANUAL (motion-adjusted) state
    where no timer runs. Only when motion clears does the timer start.
    """
    # Set up entities
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.background", "off")

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Motion Lights",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.background"],
            CONF_MOTION_ACTIVATION: False,
            CONF_EXTENDED_TIMEOUT: 60,  # 1 minute for testing
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
        # Mock startup time to simulate grace period expiry (beyond 180s)
        coordinator._startup_time = dt_util.now() - timedelta(seconds=200)

        # Manually turn on light
        with patch.object(
            coordinator.light_controller, "is_integration_context", return_value=False
        ):
            hass.states.async_set(
                "light.background", "on", attributes={"brightness": 255}
            )
            await hass.async_block_till_done()

        assert coordinator.current_state == STATE_MANUAL
        assert coordinator.timer_manager.has_active_timer("extended")

        # Wait a bit
        await hass.async_block_till_done()

        # Trigger motion - should transition to MOTION_MANUAL (no timer while motion active)
        hass.states.async_set("binary_sensor.motion", "on")
        await hass.async_block_till_done()

        # Should be in MOTION_MANUAL state with NO timer (motion keeps lights on)
        assert coordinator.current_state == STATE_MOTION_MANUAL
        assert not coordinator.timer_manager.has_active_timer("extended")

        # State should still be MOTION_MANUAL and lights still on
        assert hass.states.get("light.background").state == "on"

        # When motion clears, timer should start again
        hass.states.async_set("binary_sensor.motion", "off")
        await hass.async_block_till_done()

        # Should be back in MANUAL state with timer running
        assert coordinator.current_state == STATE_MANUAL
        assert coordinator.timer_manager.has_active_timer("extended")
    finally:
        # Clean up
        coordinator.async_cleanup_listeners()


async def test_motion_activation_disabled_pauses_timer_in_manual_off_state(
    hass: HomeAssistant,
) -> None:
    """Test that motion pauses timer in MANUAL_OFF state when motion_activation is False.

    When user turns off lights and stays in room (motion active), the extended timer
    should be paused. Only when motion clears should the timer restart.
    """
    # Set up entities
    hass.states.async_set("binary_sensor.motion", "off")
    hass.states.async_set("light.background", "on")

    config_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Motion Lights",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.background"],
            CONF_MOTION_ACTIVATION: False,
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
        # Force to MANUAL_OFF state (user turned off lights)
        coordinator.state_machine.force_state(STATE_MANUAL_OFF)
        coordinator.timer_manager.start_timer(
            "extended",
            TimerType.EXTENDED,
            coordinator._async_timer_expired,
        )

        assert coordinator.current_state == STATE_MANUAL_OFF
        assert coordinator.timer_manager.has_active_timer("extended")

        # Trigger motion - should CANCEL timer (user is present)
        hass.states.async_set("binary_sensor.motion", "on")
        await hass.async_block_till_done()

        # Should still be in MANUAL_OFF state but timer should be CANCELLED
        assert coordinator.current_state == STATE_MANUAL_OFF
        assert not coordinator.timer_manager.has_active_timer("extended")

        # Motion clears - timer should restart
        hass.states.async_set("binary_sensor.motion", "off")
        await hass.async_block_till_done()

        # Timer should be active again
        assert coordinator.current_state == STATE_MANUAL_OFF
        assert coordinator.timer_manager.has_active_timer("extended")
    finally:
        # Clean up
        coordinator.async_cleanup_listeners()
