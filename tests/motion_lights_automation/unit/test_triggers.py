"""Comprehensive tests for triggers.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.core import Event, HomeAssistant

from custom_components.motion_lights_automation.triggers import (
    MotionTrigger,
    OverrideTrigger,
    TriggerManager,
)


class TestMotionTrigger:
    """Test MotionTrigger class."""

    async def test_motion_trigger_setup(self, hass: HomeAssistant):
        """Test motion trigger setup."""
        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger = MotionTrigger(hass, config)

        # Set entity state
        hass.states.async_set("binary_sensor.motion1", "off")

        result = await trigger.async_setup()

        assert result is True

    async def test_motion_trigger_setup_missing_entities(self, hass: HomeAssistant):
        """Test motion trigger setup with missing entities."""
        config = {"entity_ids": ["binary_sensor.missing"], "enabled": True}
        trigger = MotionTrigger(hass, config)

        # Don't set state - entity doesn't exist
        result = await trigger.async_setup()

        # Should still return True (warning logged)
        assert result is True

    async def test_motion_trigger_no_entities(self, hass: HomeAssistant):
        """Test motion trigger with no entities configured."""
        config = {"entity_ids": [], "enabled": True}
        trigger = MotionTrigger(hass, config)

        result = await trigger.async_setup()
        assert result is False

    def test_motion_trigger_is_active_when_on(self, hass: HomeAssistant):
        """Test is_active when motion sensor is on."""
        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger = MotionTrigger(hass, config)

        # Set motion sensor on
        hass.states.async_set("binary_sensor.motion1", "on")

        assert trigger.is_active() is True

    def test_motion_trigger_is_active_when_off(self, hass: HomeAssistant):
        """Test is_active when motion sensor is off."""
        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger = MotionTrigger(hass, config)

        # Set motion sensor off
        hass.states.async_set("binary_sensor.motion1", "off")

        assert trigger.is_active() is False

    def test_motion_trigger_is_active_when_disabled(self, hass: HomeAssistant):
        """Test is_active when trigger is disabled."""
        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": False}
        trigger = MotionTrigger(hass, config)

        assert trigger.is_active() is False

    def test_motion_trigger_set_enabled(self, hass: HomeAssistant):
        """Test set_enabled method."""
        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger = MotionTrigger(hass, config)

        assert trigger.enabled is True

        trigger.set_enabled(False)
        assert trigger.enabled is False

    def test_motion_trigger_callbacks(self, hass: HomeAssistant):
        """Test activated/deactivated callbacks."""
        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger = MotionTrigger(hass, config)

        activated_callback = MagicMock()
        deactivated_callback = MagicMock()

        trigger.on_activated(activated_callback)
        trigger.on_deactivated(deactivated_callback)

        # Simulate motion ON event
        event = MagicMock(spec=Event)
        new_state = MagicMock()
        new_state.state = "on"
        new_state.entity_id = "binary_sensor.motion1"
        event.data = {"new_state": new_state}

        trigger._async_motion_changed(event)
        activated_callback.assert_called_once()

    def test_motion_trigger_get_info(self, hass: HomeAssistant):
        """Test get_info method."""
        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger = MotionTrigger(hass, config)

        # Set state in hass
        hass.states.async_set("binary_sensor.motion1", "off")

        info = trigger.get_info()

        assert info["type"] == "motion"
        assert info["enabled"] is True
        assert "entity_ids" in info
        assert "is_active" in info


class TestOverrideTrigger:
    """Test OverrideTrigger class."""

    async def test_override_trigger_setup(self, hass: HomeAssistant):
        """Test override trigger setup."""
        config = {"entity_id": "switch.override"}
        trigger = OverrideTrigger(hass, config)

        # Set entity exists
        hass.states.async_set("switch.override", "off")

        result = await trigger.async_setup()

        assert result is True

    async def test_override_trigger_setup_no_entity(self, hass: HomeAssistant):
        """Test override trigger setup with no entity."""
        config = {"entity_id": None}
        trigger = OverrideTrigger(hass, config)

        result = await trigger.async_setup()
        assert result is True  # Not an error, just optional

    async def test_override_trigger_setup_missing_entity(self, hass: HomeAssistant):
        """Test override trigger setup with missing entity."""
        config = {"entity_id": "switch.missing"}
        trigger = OverrideTrigger(hass, config)

        # Don't set state - entity doesn't exist
        result = await trigger.async_setup()

        # Should still succeed - will monitor once entity appears
        assert result is True
        assert trigger.is_active() is False  # Not active since entity doesn't exist

    def test_override_trigger_is_active_when_on(self, hass: HomeAssistant):
        """Test is_active when override is on."""
        config = {"entity_id": "switch.override"}
        trigger = OverrideTrigger(hass, config)

        # Set override on
        hass.states.async_set("switch.override", "on")

        assert trigger.is_active() is True

    def test_override_trigger_is_active_when_off(self, hass: HomeAssistant):
        """Test is_active when override is off."""
        config = {"entity_id": "switch.override"}
        trigger = OverrideTrigger(hass, config)

        # Set override off
        hass.states.async_set("switch.override", "off")

        assert trigger.is_active() is False

    def test_override_trigger_callbacks(self, hass: HomeAssistant):
        """Test activated/deactivated callbacks."""
        config = {"entity_id": "switch.override"}
        trigger = OverrideTrigger(hass, config)

        activated_callback = MagicMock()
        deactivated_callback = MagicMock()

        trigger.on_activated(activated_callback)
        trigger.on_deactivated(deactivated_callback)

        # Simulate override ON event
        event = MagicMock(spec=Event)
        new_state = MagicMock()
        new_state.state = "on"
        old_state = MagicMock()
        old_state.state = "off"
        event.data = {"new_state": new_state, "old_state": old_state}

        trigger._async_override_changed(event)
        activated_callback.assert_called_once()

    def test_override_trigger_get_info(self, hass: HomeAssistant):
        """Test get_info method."""
        config = {"entity_id": "switch.override"}
        trigger = OverrideTrigger(hass, config)

        # Set override state
        hass.states.async_set("switch.override", "off")

        info = trigger.get_info()

        assert info["type"] == "override"
        assert "entity_id" in info
        assert "is_active" in info


class TestTriggerManager:
    """Test TriggerManager class."""

    def test_trigger_manager_creation(self, hass: HomeAssistant):
        """Test trigger manager creation."""
        manager = TriggerManager(hass)
        assert manager is not None

    def test_add_trigger(self, hass: HomeAssistant):
        """Test adding a trigger."""
        manager = TriggerManager(hass)

        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger = MotionTrigger(hass, config)

        manager.add_trigger("motion", trigger)

        retrieved = manager.get_trigger("motion")
        assert retrieved == trigger

    def test_add_trigger_replaces_existing(self, hass: HomeAssistant):
        """Test that adding trigger with same name replaces old one."""
        manager = TriggerManager(hass)

        config1 = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger1 = MotionTrigger(hass, config1)

        config2 = {"entity_ids": ["binary_sensor.motion2"], "enabled": True}
        trigger2 = MotionTrigger(hass, config2)

        manager.add_trigger("motion", trigger1)
        manager.add_trigger("motion", trigger2)

        retrieved = manager.get_trigger("motion")
        assert retrieved == trigger2

    async def test_async_setup_all(self, hass: HomeAssistant):
        """Test setup all triggers."""
        manager = TriggerManager(hass)

        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger = MotionTrigger(hass, config)
        manager.add_trigger("motion", trigger)

        # Set entity state for setup
        hass.states.async_set("binary_sensor.motion1", "off")

        result = await manager.async_setup_all()

        assert result is True

    async def test_async_setup_all_with_failure(self, hass: HomeAssistant):
        """Test setup all triggers with one failure."""
        manager = TriggerManager(hass)

        config1 = {"entity_ids": [], "enabled": True}  # Will fail
        trigger1 = MotionTrigger(hass, config1)
        manager.add_trigger("motion", trigger1)

        result = await manager.async_setup_all()
        assert result is False

    def test_get_trigger(self, hass: HomeAssistant):
        """Test get_trigger method."""
        manager = TriggerManager(hass)

        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger = MotionTrigger(hass, config)
        manager.add_trigger("motion", trigger)

        retrieved = manager.get_trigger("motion")
        assert retrieved is not None

        nonexistent = manager.get_trigger("nonexistent")
        assert nonexistent is None

    def test_is_trigger_active(self, hass: HomeAssistant):
        """Test is_trigger_active method."""
        manager = TriggerManager(hass)

        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger = MotionTrigger(hass, config)
        manager.add_trigger("motion", trigger)

        # Set motion sensor on
        hass.states.async_set("binary_sensor.motion1", "on")

        assert manager.is_trigger_active("motion") is True

    def test_cleanup_all(self, hass: HomeAssistant):
        """Test cleanup_all method."""
        manager = TriggerManager(hass)

        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger = MotionTrigger(hass, config)
        trigger.cleanup = MagicMock()

        manager.add_trigger("motion", trigger)
        manager.cleanup_all()

        trigger.cleanup.assert_called_once()
        assert len(manager._triggers) == 0

    def test_get_info(self, hass: HomeAssistant):
        """Test get_info method."""
        manager = TriggerManager(hass)

        config = {"entity_ids": ["binary_sensor.motion1"], "enabled": True}
        trigger = MotionTrigger(hass, config)
        manager.add_trigger("motion", trigger)

        # Set motion sensor state
        hass.states.async_set("binary_sensor.motion1", "off")

        info = manager.get_info()

        assert "total_triggers" in info
        assert info["total_triggers"] == 1
        assert "triggers" in info
