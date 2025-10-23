"""Comprehensive tests for light_controller.py."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from homeassistant.core import HomeAssistant, Context
from tests.common import async_mock_service




from homeassistant.components.motion_lights_automation.light_controller import (
    LightController,
    LightState,
    TimeOfDayBrightnessStrategy,
    TimeOfDayLightSelectionStrategy,
    BrightnessStrategy,
    LightSelectionStrategy,
)


class TestLightState:
    """Test LightState class."""

    def test_light_state_creation(self):
        """Test LightState creation."""
        state = LightState("light.test", True, 50)
        assert state.entity_id == "light.test"
        assert state.is_on is True
        assert state.brightness_pct == 50

    def test_light_state_from_ha_state_on(self):
        """Test LightState from HA state (on)."""
        ha_state = MagicMock()
        ha_state.state = "on"
        ha_state.attributes = {"brightness": 128}
        
        light_state = LightState.from_ha_state("light.test", ha_state)
        assert light_state.is_on is True
        assert light_state.brightness_pct == 50  # 128/255 * 100

    def test_light_state_from_ha_state_off(self):
        """Test LightState from HA state (off)."""
        ha_state = MagicMock()
        ha_state.state = "off"
        ha_state.attributes = {}
        
        light_state = LightState.from_ha_state("light.test", ha_state)
        assert light_state.is_on is False
        assert light_state.brightness_pct == 0


class TestBrightnessStrategy:
    """Test brightness strategies."""

    def test_time_of_day_strategy_day(self):
        """Test TimeOfDayBrightnessStrategy for active mode."""
        strategy = TimeOfDayBrightnessStrategy(active_brightness=60, inactive_brightness=10)
        brightness = strategy.get_brightness({"is_inactive": False})
        assert brightness == 60

    def test_time_of_day_strategy_night(self):
        """Test TimeOfDayBrightnessStrategy for inactive mode."""
        strategy = TimeOfDayBrightnessStrategy(active_brightness=60, inactive_brightness=10)
        brightness = strategy.get_brightness({"is_inactive": True})
        assert brightness == 10

    def test_custom_brightness_strategy(self):
        """Test custom brightness strategy."""
        class CustomStrategy(BrightnessStrategy):
            def get_brightness(self, context):
                return 75
        
        strategy = CustomStrategy()
        brightness = strategy.get_brightness({})
        assert brightness == 75


class TestLightSelectionStrategy:
    """Test light selection strategies."""

    def test_time_of_day_selection_day(self):
        """Test TimeOfDayLightSelectionStrategy for day."""
        strategy = TimeOfDayLightSelectionStrategy()
        lights = {
            "ceiling": ["light.c1", "light.c2"],
            "background": ["light.bg"],
            "feature": ["light.f1"],
        }
        
        selected = strategy.select_lights(lights, {"is_night": False})
        assert "light.c1" in selected
        assert "light.c2" in selected
        assert "light.bg" in selected
        assert "light.f1" in selected

    def test_time_of_day_selection_night(self):
        """Test TimeOfDayLightSelectionStrategy for night."""
        strategy = TimeOfDayLightSelectionStrategy()
        lights = {
            "ceiling": ["light.c1"],
            "background": ["light.bg"],
        }
        
        selected = strategy.select_lights(lights, {"is_night": True})
        assert selected == ["light.bg"]
        assert "light.c1" not in selected

    def test_custom_selection_strategy(self):
        """Test custom selection strategy."""
        class CustomStrategy(LightSelectionStrategy):
            def select_lights(self, all_lights, context):
                return ["light.custom"]
        
        strategy = CustomStrategy()
        selected = strategy.select_lights({}, {})
        assert selected == ["light.custom"]


class TestLightController:
    """Test LightController class."""

    def test_light_controller_creation(self, hass: HomeAssistant):
        """Test LightController creation."""
        light_groups = {"ceiling": ["light.c1"], "background": ["light.bg"]}
        controller = LightController(hass, light_groups)
        assert controller is not None

    def test_get_all_lights(self, hass: HomeAssistant):
        """Test get_all_lights method."""
        light_groups = {
            "ceiling": ["light.c1", "light.c2"],
            "background": ["light.bg"],
        }
        controller = LightController(hass, light_groups)
        
        all_lights = controller.get_all_lights()
        assert "light.c1" in all_lights
        assert "light.c2" in all_lights
        assert "light.bg" in all_lights
        assert len(all_lights) == 3

    def test_get_all_lights_removes_duplicates(self, hass: HomeAssistant):
        """Test get_all_lights removes duplicates."""
        light_groups = {
            "ceiling": ["light.c1", "light.c1"],
            "background": ["light.c1"],
        }
        controller = LightController(hass, light_groups)
        
        all_lights = controller.get_all_lights()
        assert all_lights.count("light.c1") == 1

    def test_update_light_state(self, hass: HomeAssistant):
        """Test update_light_state method."""
        controller = LightController(hass, {})
        
        ha_state = MagicMock()
        ha_state.state = "on"
        ha_state.attributes = {"brightness": 128}
        
        light_state = controller.update_light_state("light.test", ha_state)
        assert light_state.is_on is True
        assert light_state.brightness_pct == 50

    def test_get_light_state(self, hass: HomeAssistant):
        """Test get_light_state method."""
        controller = LightController(hass, {})
        
        ha_state = MagicMock()
        ha_state.state = "on"
        ha_state.attributes = {"brightness": 128}
        
        controller.update_light_state("light.test", ha_state)
        light_state = controller.get_light_state("light.test")
        
        assert light_state is not None
        assert light_state.entity_id == "light.test"

    def test_any_lights_on(self, hass: HomeAssistant):
        """Test any_lights_on method."""
        controller = LightController(hass, {})
        
        # No lights tracked yet
        assert controller.any_lights_on() is False
        
        # Add an off light
        ha_state = MagicMock()
        ha_state.state = "off"
        ha_state.attributes = {}
        controller.update_light_state("light.off", ha_state)
        assert controller.any_lights_on() is False
        
        # Add an on light
        ha_state.state = "on"
        ha_state.attributes = {"brightness": 100}
        controller.update_light_state("light.on", ha_state)
        assert controller.any_lights_on() is True

    def test_refresh_all_states(self, hass: HomeAssistant):
        """Test refresh_all_states method."""
        light_groups = {"ceiling": ["light.c1", "light.c2"]}
        controller = LightController(hass, light_groups)
        
        # Mock states directly
        mock_state = MagicMock()
        mock_state.state = "on"
        mock_state.attributes = {"brightness": 128}
        
        hass.states.async_set("light.c1", "on", {"brightness": 128})
        hass.states.async_set("light.c2", "on", {"brightness": 128})
        
        controller.refresh_all_states()
        
        # Should have tracked states for both lights
        assert controller.get_light_state("light.c1") is not None
        assert controller.get_light_state("light.c2") is not None

    async def test_turn_on_auto_lights(self, hass: HomeAssistant):
        """Test turn_on_auto_lights method."""
        light_groups = {"ceiling": ["light.c1"]}
        controller = LightController(hass, light_groups)
        
        # Set state in hass
        hass.states.async_set("light.c1", "off", {})
        
        # Mock the light service
        calls = async_mock_service(hass, "light", "turn_on")
        
        turned_on = await controller.turn_on_auto_lights({"is_night": False})
        
        assert "light.c1" in turned_on
        assert len(calls) == 1
        assert calls[0].domain == "light"
        assert calls[0].service == "turn_on"

    async def test_turn_on_auto_lights_skips_already_on(self, hass: HomeAssistant):
        """Test turn_on_auto_lights skips already-on lights."""
        light_groups = {"ceiling": ["light.c1"]}
        controller = LightController(hass, light_groups)
        
        # Set light already on
        hass.states.async_set("light.c1", "on", {"brightness": 128})
        
        # Mock the light service
        calls = async_mock_service(hass, "light", "turn_on")
        
        turned_on = await controller.turn_on_auto_lights({"is_night": False})
        
        # Should not turn on already-on lights
        assert len(turned_on) == 0
        assert len(calls) == 0

    async def test_turn_off_lights(self, hass: HomeAssistant):
        """Test turn_off_lights method."""
        light_groups = {"ceiling": ["light.c1"]}
        controller = LightController(hass, light_groups)
        
        # Set light on
        hass.states.async_set("light.c1", "on", {"brightness": 128})
        
        # Mock the light service
        calls = async_mock_service(hass, "light", "turn_off")
        
        turned_off = await controller.turn_off_lights()
        
        assert "light.c1" in turned_off
        assert len(calls) == 1
        assert calls[0].domain == "light"
        assert calls[0].service == "turn_off"

    async def test_turn_off_lights_skips_already_off(self, hass: HomeAssistant):
        """Test turn_off_lights skips already-off lights."""
        light_groups = {"ceiling": ["light.c1"]}
        controller = LightController(hass, light_groups)
        
        # Set light already off
        hass.states.async_set("light.c1", "off", {})
        
        # Mock the light service
        calls = async_mock_service(hass, "light", "turn_off")
        
        turned_off = await controller.turn_off_lights()
        
        assert len(turned_off) == 0
        assert len(calls) == 0

    def test_set_brightness_strategy(self, hass: HomeAssistant):
        """Test set_brightness_strategy method."""
        controller = LightController(hass, {})
        
        new_strategy = TimeOfDayBrightnessStrategy(active_brightness=80, inactive_brightness=20)
        controller.set_brightness_strategy(new_strategy)
        
        assert controller._brightness_strategy == new_strategy

    def test_set_light_selection_strategy(self, hass: HomeAssistant):
        """Test set_light_selection_strategy method."""
        controller = LightController(hass, {})
        
        new_strategy = TimeOfDayLightSelectionStrategy()
        controller.set_light_selection_strategy(new_strategy)
        
        assert controller._light_selection_strategy == new_strategy

    def test_get_info(self, hass: HomeAssistant):
        """Test get_info method."""
        light_groups = {"ceiling": ["light.c1"], "background": ["light.bg"]}
        controller = LightController(hass, light_groups)
        
        info = controller.get_info()
        assert "light_groups" in info
        assert "total_lights" in info
        assert "lights_on" in info
        assert info["total_lights"] == 2

    def test_cleanup_old_contexts(self, hass: HomeAssistant):
        """Test cleanup_old_contexts method."""
        controller = LightController(hass, {})
        
        # Add many contexts
        for i in range(150):
            controller._context_tracking.add(f"context_{i}")
        
        assert len(controller._context_tracking) == 150
        
        controller.cleanup_old_contexts()
        assert len(controller._context_tracking) == 100
