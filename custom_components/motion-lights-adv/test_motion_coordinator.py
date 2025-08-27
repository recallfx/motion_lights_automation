"""Tests for motion coordinator core functionality (clean version)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import Context, HomeAssistant

from .const import (
    CONF_BACKGROUND_LIGHT,
    CONF_BRIGHTNESS_DAY,
    CONF_BRIGHTNESS_NIGHT,
    CONF_CEILING_LIGHT,
    CONF_DARK_OUTSIDE,
    CONF_EXTENDED_TIMEOUT,
    CONF_FEATURE_LIGHT,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
)
from .motion_coordinator import (
    MotionLightsCoordinator,
    STATE_AUTO,
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_MOTION_AUTO,
    STATE_MOTION_MANUAL,
    STATE_OVERRIDDEN,
    TIMER_EXTENDED,
    TIMER_MOTION,
)


@pytest.fixture
def mock_hass() -> HomeAssistant:
    """Minimal HomeAssistant mock for coordinator unit tests."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    hass = MagicMock(spec=HomeAssistant)
    # States
    hass.states = MagicMock()
    default_state = MagicMock(state="off")
    default_state.attributes = {}
    hass.states.get = MagicMock(return_value=default_state)
    # Services
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock(return_value=None)
    # Loop / scheduling
    hass.loop = loop
    hass.async_create_task = lambda coro: loop.create_task(coro)
    return hass


@pytest.fixture
def coordinator(mock_hass: HomeAssistant) -> MotionLightsCoordinator:
    """Coordinator with default configuration."""
    data = {
        CONF_MOTION_ENTITY: "binary_sensor.motion",
        CONF_OVERRIDE_SWITCH: "input_boolean.override",
        CONF_BACKGROUND_LIGHT: "light.background",
        CONF_FEATURE_LIGHT: "light.feature",
        CONF_CEILING_LIGHT: "light.ceiling",
        CONF_DARK_OUTSIDE: "binary_sensor.dark_outside",
        CONF_MOTION_ACTIVATION: True,
        CONF_NO_MOTION_WAIT: 120,
        CONF_EXTENDED_TIMEOUT: 600,
        CONF_BRIGHTNESS_DAY: 60,
        CONF_BRIGHTNESS_NIGHT: 10,
    }
    entry = MagicMock()
    entry.data = data
    return MotionLightsCoordinator(mock_hass, entry)


class TestCoreTask1_AutomaticLightOn:
    def test_motion_on_idle_turns_on_and_sets_motion_auto(self, coordinator, mock_hass):
        coordinator._current_state = STATE_IDLE
        mock_hass.states.get.side_effect = lambda eid: MagicMock(state="off")
        coordinator._async_turn_on_tod_lights = AsyncMock()

        coordinator._handle_motion_on()

        assert coordinator._current_state == STATE_MOTION_AUTO
        coordinator._async_turn_on_tod_lights.assert_called_once()

    def test_motion_on_ignored_when_overridden(self, coordinator, mock_hass):
        coordinator._current_state = STATE_OVERRIDDEN
        coordinator._async_turn_on_tod_lights = AsyncMock()

        coordinator._handle_motion_on()

        assert coordinator._current_state == STATE_OVERRIDDEN
        coordinator._async_turn_on_tod_lights.assert_not_called()

    def test_motion_on_with_activation_disabled_treats_as_manual(
        self, coordinator, mock_hass
    ):
        coordinator.motion_activation = False
        coordinator._current_state = STATE_IDLE
        mock_hass.states.get.side_effect = lambda eid: MagicMock(state="on")
        coordinator._async_turn_on_tod_lights = AsyncMock()

        coordinator._handle_motion_on()

        assert coordinator._current_state == STATE_MANUAL
        coordinator._async_turn_on_tod_lights.assert_not_called()

    def test_motion_on_while_manual_cancels_timer_no_light_change(self, coordinator):
        coordinator._current_state = STATE_MANUAL
        coordinator._active_timer = MagicMock()
        coordinator._timer_type = TIMER_EXTENDED
        coordinator._async_turn_on_tod_lights = AsyncMock()

        coordinator._handle_motion_on()

        assert coordinator._current_state == STATE_MOTION_MANUAL
        assert coordinator._active_timer is None
        coordinator._async_turn_on_tod_lights.assert_not_called()


class TestCoreTask2_AutomaticLightOff:
    def test_motion_off_from_motion_auto_starts_motion_timer(
        self, coordinator, mock_hass
    ):
        coordinator._current_state = STATE_MOTION_AUTO
        coordinator.motion_activation = True
        mock_hass.states.get.side_effect = lambda eid: MagicMock(state="on")

        coordinator._handle_motion_off()

        assert coordinator._current_state == STATE_AUTO
        assert coordinator._timer_type == TIMER_MOTION
        assert coordinator._active_timer is not None

    def test_motion_off_with_no_lights_goes_idle(self, coordinator, mock_hass):
        coordinator._current_state = STATE_MOTION_AUTO
        mock_hass.states.get.side_effect = lambda eid: MagicMock(state="off")

        coordinator._handle_motion_off()

        assert coordinator._current_state == STATE_IDLE
        assert coordinator._active_timer is None

    @pytest.mark.asyncio
    async def test_timer_expiration_turns_lights_off(self, coordinator):
        coordinator._current_state = STATE_AUTO
        coordinator._timer_type = TIMER_MOTION
        coordinator._async_turn_off_configured_lights = AsyncMock()

        await coordinator._async_timer_expired(TIMER_MOTION)

        assert coordinator._current_state == STATE_IDLE
        coordinator._async_turn_off_configured_lights.assert_called_once()
        assert coordinator._active_timer is None


class TestManualDetection:
    def test_external_light_change_during_motion_auto_switches_to_motion_manual(
        self, coordinator
    ):
        coordinator._current_state = STATE_MOTION_AUTO

        old_state = MagicMock(state="on")
        old_state.attributes = {"brightness": 128}
        new_state = MagicMock(state="on")
        new_state.attributes = {"brightness": 255}
        new_state.context = Context()

        coordinator._handle_external_light_change(
            "light.background", old_state, new_state, 50
        )

        assert coordinator._current_state == STATE_MOTION_MANUAL
        assert "external change during motion" in (
            coordinator._last_manual_reason or ""
        )

    def test_external_light_change_during_auto_switches_to_manual_with_extended_timer(
        self, coordinator
    ):
        coordinator._current_state = STATE_AUTO
        coordinator._active_timer = MagicMock()
        coordinator._timer_type = TIMER_MOTION

        old_state = MagicMock(state="off")
        new_state = MagicMock(state="on")
        new_state.context = Context()

        coordinator._handle_external_light_change(
            "light.combined", old_state, new_state, 0
        )

        assert coordinator._current_state == STATE_MANUAL
        assert coordinator._timer_type == TIMER_EXTENDED

    def test_external_light_off_during_auto_switches_to_manual_off_with_extended_timer(
        self, coordinator
    ):
        coordinator._current_state = STATE_AUTO
        coordinator._active_timer = MagicMock()
        coordinator._timer_type = TIMER_MOTION

        old_state = MagicMock(state="on")
        new_state = MagicMock(state="off")
        new_state.context = Context()

        coordinator._handle_external_light_change(
            "light.combined", old_state, new_state, 0
        )

        assert coordinator._current_state == STATE_MANUAL_OFF
        assert coordinator._timer_type == TIMER_EXTENDED

    def test_motion_ignored_during_manual_off(self, coordinator):
        coordinator._current_state = STATE_MANUAL_OFF
        coordinator._active_timer = MagicMock()
        coordinator._timer_type = TIMER_EXTENDED

        coordinator._handle_motion_on()

        # State and timer remain unchanged
        assert coordinator._current_state == STATE_MANUAL_OFF
        assert coordinator._timer_type == TIMER_EXTENDED

    def test_idle_external_on_goes_manual_with_extended_timer(self, coordinator):
        coordinator._current_state = STATE_IDLE

        old_state = MagicMock(state="off")
        new_state = MagicMock(state="on")
        new_state.context = Context()

        coordinator._handle_external_light_change(
            "light.combined", old_state, new_state, 0
        )

        assert coordinator._current_state == STATE_MANUAL
        assert coordinator._timer_type == TIMER_EXTENDED


class TestLightSelection:
    @patch("homeassistant.util.dt.now")
    def test_night_uses_night_brightness(self, mock_now, coordinator):
        mock_now.return_value = datetime(2025, 8, 14, 2, 0, 0)
        # Mock dark outside entity as "on" (night mode)
        coordinator.hass.states.get.return_value.state = "on"
        lights, brightness = coordinator._determine_lights_and_brightness()
        assert lights == [coordinator.background_light]
        assert brightness == coordinator.brightness_night

    @patch("homeassistant.util.dt.now")
    def test_day_uses_day_brightness(self, mock_now, coordinator):
        mock_now.return_value = datetime(2025, 8, 14, 12, 0, 0)
        # Mock dark outside entity as "off" (day mode)
        coordinator.hass.states.get.return_value.state = "off"
        lights, brightness = coordinator._determine_lights_and_brightness()
        expected_lights = [
            coordinator.background_light,
            coordinator.feature_light,
            coordinator.ceiling_light,
        ]
        assert lights == expected_lights
        assert brightness == coordinator.brightness_day


class TestTimerBehavior:
    """Test timer behavior with motion events."""

    def test_new_motion_during_auto_cancels_timer(self, coordinator, mock_hass):
        """Test that new motion during auto mode cancels existing timer."""
        coordinator._current_state = STATE_AUTO
        coordinator._active_timer = MagicMock()
        coordinator._timer_type = TIMER_MOTION
        mock_hass.states.get.side_effect = lambda eid: MagicMock(state="on")

        # Simulate motion on event
        event = MagicMock()
        event.data = {"new_state": MagicMock(state="on")}
        coordinator._async_motion_state_changed(event)

        assert coordinator.current_state == STATE_MOTION_AUTO
        assert coordinator._active_timer is None

    def test_new_motion_during_manual_cancels_extended_timer(self, coordinator):
        """Test that new motion during manual mode cancels extended timer."""
        coordinator._current_state = STATE_MANUAL
        coordinator._active_timer = MagicMock()
        coordinator._timer_type = TIMER_EXTENDED

        # Simulate motion on event
        event = MagicMock()
        event.data = {"new_state": MagicMock(state="on")}
        coordinator._async_motion_state_changed(event)

        assert coordinator.current_state == STATE_MOTION_MANUAL
        assert coordinator._active_timer is None
