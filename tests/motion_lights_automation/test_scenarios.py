"""Scenario tests for Motion Lights Automation.

These tests verify complete user scenarios by testing the coordinator
with mocked Home Assistant entities, ensuring all components work together.
"""

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
    CONF_NO_MOTION_WAIT,
    DOMAIN,
    STATE_AUTO,
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_MOTION_AUTO,
    STATE_MOTION_MANUAL,
)
from custom_components.motion_lights_automation.motion_coordinator import (
    MotionLightsCoordinator,
)


@pytest.fixture
def config_entry() -> ConfigEntry:
    """Create a config entry for testing."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Motion Lights",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.ceiling"],
            CONF_MOTION_ACTIVATION: True,
            CONF_NO_MOTION_WAIT: 300,
            CONF_EXTENDED_TIMEOUT: 1200,
        },
        options={},
        entry_id="test_entry_id",
        source="user",
        unique_id=None,
        discovery_keys={},
    )


class TestManualOffScenarios:
    """Tests for when user manually turns off lights."""

    async def test_user_turns_off_light_during_motion_stays_off(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Test that lights stay off when user turns them off during active motion.
        
        This is the critical bug fix test:
        1. Motion detected -> lights turn on (MOTION_AUTO)
        2. User manually turns off light
        3. System should go to MANUAL_OFF (not back to MOTION_AUTO)
        4. Lights should stay off despite motion still being active
        """
        # Set up entities
        hass.states.async_set("binary_sensor.motion", "on")
        hass.states.async_set("light.ceiling", "off")

        coordinator = MotionLightsCoordinator(hass, config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Skip startup grace period
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)

            # Simulate motion turning on lights -> MOTION_AUTO
            coordinator.state_machine.force_state(STATE_MOTION_AUTO)
            hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})
            coordinator.light_controller.refresh_all_states()

            assert coordinator.current_state == STATE_MOTION_AUTO
            assert coordinator.light_controller.any_lights_on()

            # User manually turns off the light
            with patch.object(
                coordinator.light_controller, "is_integration_context", return_value=False
            ):
                hass.states.async_set("light.ceiling", "off")
                await hass.async_block_till_done()

            # Should be in MANUAL_OFF, NOT back to MOTION_AUTO
            assert coordinator.current_state == STATE_MANUAL_OFF, (
                f"Expected MANUAL_OFF but got {coordinator.current_state}. "
                "Lights should stay off when user turns them off during motion."
            )

            # Verify extended timer is active
            assert coordinator.timer_manager.has_active_timer("extended")

        finally:
            coordinator.async_cleanup_listeners()

    async def test_motion_does_not_reactivate_lights_in_manual_off(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Test that motion events don't turn lights back on in MANUAL_OFF state."""
        from custom_components.motion_lights_automation.timer_manager import TimerType

        # Set up entities
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.ceiling", "off")

        coordinator = MotionLightsCoordinator(hass, config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Skip startup grace period
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)

            # Start in MANUAL_OFF state (user already turned off lights)
            coordinator.state_machine.force_state(STATE_MANUAL_OFF)
            coordinator.timer_manager.start_timer(
                "extended",
                TimerType.EXTENDED,
                coordinator._async_timer_expired,
            )

            # Motion is detected
            hass.states.async_set("binary_sensor.motion", "on")
            await hass.async_block_till_done()

            # Should still be in MANUAL_OFF
            assert coordinator.current_state == STATE_MANUAL_OFF, (
                f"Expected MANUAL_OFF but got {coordinator.current_state}. "
                "Motion should not reactivate lights when user has turned them off."
            )

        finally:
            coordinator.async_cleanup_listeners()

    async def test_user_turns_off_one_light_others_stay_on(
        self, hass: HomeAssistant
    ) -> None:
        """Test that turning off one light doesn't trigger MANUAL_OFF if others are still on."""
        config_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Test Motion Lights",
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.ceiling", "light.lamp"],
                CONF_MOTION_ACTIVATION: True,
            },
            options={},
            entry_id="test_entry_id",
            source="user",
            unique_id=None,
            discovery_keys={},
        )

        # Set up entities
        hass.states.async_set("binary_sensor.motion", "on")
        hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})
        hass.states.async_set("light.lamp", "on", attributes={"brightness": 200})

        coordinator = MotionLightsCoordinator(hass, config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Skip startup grace period
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)

            # Start in MOTION_AUTO
            coordinator.state_machine.force_state(STATE_MOTION_AUTO)
            coordinator.light_controller.refresh_all_states()

            # User turns off one light (but lamp stays on)
            with patch.object(
                coordinator.light_controller, "is_integration_context", return_value=False
            ):
                hass.states.async_set("light.ceiling", "off")
                await hass.async_block_till_done()

            # Should be MOTION_MANUAL (not MANUAL_OFF) because lamp is still on
            assert coordinator.current_state == STATE_MOTION_MANUAL

        finally:
            coordinator.async_cleanup_listeners()


class TestMotionCycleScenarios:
    """Tests for complete motion detection cycles."""

    async def test_motion_on_off_cycle_turns_off_lights(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Test complete motion cycle: motion on -> off -> timer expires -> lights off."""
        # Set up entities
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.ceiling", "off")

        coordinator = MotionLightsCoordinator(hass, config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Skip startup grace period
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)

            # Motion detected
            hass.states.async_set("binary_sensor.motion", "on")
            await hass.async_block_till_done()

            assert coordinator.current_state == STATE_MOTION_AUTO

            # Motion stops
            hass.states.async_set("binary_sensor.motion", "off")
            await hass.async_block_till_done()

            assert coordinator.current_state == STATE_AUTO
            assert coordinator.timer_manager.has_active_timer("motion")

        finally:
            coordinator.async_cleanup_listeners()

    async def test_motion_restart_during_auto_cancels_timer(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Test that new motion during AUTO state cancels timer and goes back to MOTION_AUTO."""
        # Set up entities
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})

        coordinator = MotionLightsCoordinator(hass, config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Skip startup grace period
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)

            # Start in AUTO state with timer running
            coordinator.state_machine.force_state(STATE_AUTO)
            coordinator.light_controller.refresh_all_states()

            # Motion detected again
            hass.states.async_set("binary_sensor.motion", "on")
            await hass.async_block_till_done()

            assert coordinator.current_state == STATE_MOTION_AUTO

        finally:
            coordinator.async_cleanup_listeners()


class TestManualBrightnessScenarios:
    """Tests for manual brightness adjustment scenarios."""

    async def test_brightness_change_triggers_manual_state(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Test that significant brightness change triggers transition to manual state."""
        # Set up entities
        hass.states.async_set("binary_sensor.motion", "on")
        hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})

        coordinator = MotionLightsCoordinator(hass, config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Skip startup grace period
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)

            # Start in MOTION_AUTO
            coordinator.state_machine.force_state(STATE_MOTION_AUTO)
            coordinator.light_controller.refresh_all_states()

            # User changes brightness significantly
            with patch.object(
                coordinator.light_controller, "is_integration_context", return_value=False
            ):
                hass.states.async_set("light.ceiling", "on", attributes={"brightness": 50})
                await hass.async_block_till_done()

            # Should be in MOTION_MANUAL (brightness change, not off)
            assert coordinator.current_state == STATE_MOTION_MANUAL

        finally:
            coordinator.async_cleanup_listeners()

    async def test_motion_off_after_manual_adjustment_starts_extended_timer(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Test that extended timer starts when motion stops after manual adjustment."""
        # Set up entities
        hass.states.async_set("binary_sensor.motion", "on")
        hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})

        coordinator = MotionLightsCoordinator(hass, config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Skip startup grace period
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)

            # Start in MOTION_MANUAL (user already adjusted)
            coordinator.state_machine.force_state(STATE_MOTION_MANUAL)
            coordinator.light_controller.refresh_all_states()

            # Motion stops
            hass.states.async_set("binary_sensor.motion", "off")
            await hass.async_block_till_done()

            # Should be in MANUAL with extended timer
            assert coordinator.current_state == STATE_MANUAL
            assert coordinator.timer_manager.has_active_timer("extended")

        finally:
            coordinator.async_cleanup_listeners()


class TestTimerExpiryScenarios:
    """Tests for timer expiry scenarios."""

    async def test_manual_off_timer_expires_returns_to_idle(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Test that MANUAL_OFF returns to IDLE when extended timer expires."""
        # Set up entities
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.ceiling", "off")

        coordinator = MotionLightsCoordinator(hass, config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Start in MANUAL_OFF
            coordinator.state_machine.force_state(STATE_MANUAL_OFF)

            # Simulate timer expiry
            await coordinator._async_timer_expired("extended")

            # Should be in IDLE now
            assert coordinator.current_state == STATE_IDLE

        finally:
            coordinator.async_cleanup_listeners()

    async def test_idle_after_manual_off_allows_motion_activation(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Test that motion works again after MANUAL_OFF -> IDLE transition."""
        # Set up entities
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.ceiling", "off")

        coordinator = MotionLightsCoordinator(hass, config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Skip startup grace period
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)

            # Start in IDLE (simulating post-MANUAL_OFF timeout)
            coordinator.state_machine.force_state(STATE_IDLE)

            # Motion detected
            hass.states.async_set("binary_sensor.motion", "on")
            await hass.async_block_till_done()

            # Should activate normally
            assert coordinator.current_state == STATE_MOTION_AUTO

        finally:
            coordinator.async_cleanup_listeners()
