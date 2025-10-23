"""Trigger handlers for motion lights automation.

This module provides a pluggable trigger system that can be easily extended
with new trigger types (door sensors, presence detection, schedules, etc.)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable
import logging

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

_LOGGER = logging.getLogger(__name__)


class TriggerHandler(ABC):
    """Abstract base class for trigger handlers.
    
    Implement this interface to create new trigger types for the automation.
    Each trigger handler monitors specific entities/events and calls callbacks
    when trigger conditions are met.
    
    Examples of trigger handlers:
    - MotionTrigger (motion sensors)
    - DoorTrigger (door sensors)
    - PresenceTrigger (presence detection)
    - ScheduleTrigger (time-based)
    - LuxTrigger (ambient light level)
    """

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]):
        """Initialize the trigger handler.
        
        Args:
            hass: HomeAssistant instance
            config: Configuration for this trigger
        """
        self.hass = hass
        self.config = config
        self._callbacks: dict[str, list[Callable]] = {
            "activated": [],
            "deactivated": [],
        }
        self._unsubscribers: list[Callable] = []

    @abstractmethod
    async def async_setup(self) -> bool:
        """Set up the trigger handler.
        
        This should set up event listeners and any required monitoring.
        
        Returns:
            True if setup successful, False otherwise
        """
        pass

    @abstractmethod
    def is_active(self) -> bool:
        """Check if the trigger is currently active.
        
        Returns:
            True if trigger is active, False otherwise
        """
        pass

    def on_activated(self, callback: Callable) -> None:
        """Register a callback for when trigger activates."""
        self._callbacks["activated"].append(callback)

    def on_deactivated(self, callback: Callable) -> None:
        """Register a callback for when trigger deactivates."""
        self._callbacks["deactivated"].append(callback)

    def _fire_activated(self) -> None:
        """Fire all activated callbacks."""
        for callback in self._callbacks["activated"]:
            try:
                callback()
            except Exception as err:
                _LOGGER.error("Error in trigger activated callback: %s", err)

    def _fire_deactivated(self) -> None:
        """Fire all deactivated callbacks."""
        for callback in self._callbacks["deactivated"]:
            try:
                callback()
            except Exception as err:
                _LOGGER.error("Error in trigger deactivated callback: %s", err)

    def cleanup(self) -> None:
        """Clean up event listeners and resources."""
        for unsub in self._unsubscribers:
            unsub()
        self._unsubscribers.clear()

    @abstractmethod
    def get_info(self) -> dict[str, Any]:
        """Get diagnostic information about this trigger."""
        pass


class MotionTrigger(TriggerHandler):
    """Trigger handler for motion sensors.
    
    Monitors one or more motion sensors and fires callbacks when motion
    is detected or clears.
    """

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]):
        """Initialize motion trigger.
        
        Config should contain:
            - entity_ids: List of motion sensor entity IDs
            - enabled: Whether motion detection is enabled (default: True)
        """
        super().__init__(hass, config)
        self.entity_ids = config.get("entity_ids", [])
        self.enabled = config.get("enabled", True)

    async def async_setup(self) -> bool:
        """Set up motion sensor monitoring."""
        if not self.entity_ids:
            _LOGGER.warning("No motion sensors configured")
            return False
        
        # Verify entities exist (warn but continue)
        missing = [eid for eid in self.entity_ids if not self.hass.states.get(eid)]
        if missing:
            _LOGGER.warning(
                "Motion sensors not yet available: %s (will monitor once they appear)",
                missing
            )
        
        # Set up state change tracking (works even if entities don't exist yet)
        self._unsubscribers.append(
            async_track_state_change_event(
                self.hass,
                self.entity_ids,
                self._async_motion_changed,
            )
        )
        
        _LOGGER.info("Motion trigger set up for %d sensors", len(self.entity_ids))
        return True

    @callback
    def _async_motion_changed(self, event: Event) -> None:
        """Handle motion sensor state change."""
        if not self.enabled:
            return
        
        new_state = event.data.get("new_state")
        if not new_state:
            return
        
        if new_state.state == "on":
            _LOGGER.debug("Motion detected on %s", new_state.entity_id)
            self._fire_activated()
        elif new_state.state == "off":
            # Only fire deactivated if ALL sensors are off
            if not self.is_active():
                _LOGGER.debug("All motion sensors clear")
                self._fire_deactivated()

    def is_active(self) -> bool:
        """Check if any motion sensor is currently active."""
        if not self.enabled:
            return False
        
        return any(
            (state := self.hass.states.get(eid)) and state.state == "on"
            for eid in self.entity_ids
        )

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable motion detection."""
        if self.enabled != enabled:
            self.enabled = enabled
            _LOGGER.info("Motion trigger %s", "enabled" if enabled else "disabled")

    def get_info(self) -> dict[str, Any]:
        """Get diagnostic information."""
        return {
            "type": "motion",
            "enabled": self.enabled,
            "entity_ids": self.entity_ids,
            "is_active": self.is_active(),
            "sensor_states": {
                eid: self.hass.states.get(eid).state if self.hass.states.get(eid) else "unknown"
                for eid in self.entity_ids
            },
        }


class OverrideTrigger(TriggerHandler):
    """Trigger handler for override switch.
    
    Monitors an override switch that can disable all automation.
    """

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]):
        """Initialize override trigger.
        
        Config should contain:
            - entity_id: Override switch entity ID
        """
        super().__init__(hass, config)
        self.entity_id = config.get("entity_id")

    async def async_setup(self) -> bool:
        """Set up override switch monitoring."""
        if not self.entity_id:
            _LOGGER.info("No override switch configured")
            return True  # Not an error, just optional
        
        # Check if entity exists (warn but continue)
        state = self.hass.states.get(self.entity_id)
        if not state:
            _LOGGER.warning(
                "Override switch not yet available: %s (will monitor once it appears)",
                self.entity_id
            )
        
        # Set up listener (works even if entity doesn't exist yet)
        self._unsubscribers.append(
            async_track_state_change_event(
                self.hass,
                [self.entity_id],
                self._async_override_changed,
            )
        )
        
        _LOGGER.info("Override trigger set up for %s", self.entity_id)
        return True

    @callback
    def _async_override_changed(self, event: Event) -> None:
        """Handle override switch state change."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        
        if not new_state or not old_state:
            return
        
        if new_state.state == "on" and old_state.state == "off":
            _LOGGER.info("Override activated")
            self._fire_activated()
        elif new_state.state == "off" and old_state.state == "on":
            _LOGGER.info("Override deactivated")
            self._fire_deactivated()

    def is_active(self) -> bool:
        """Check if override is currently active."""
        if not self.entity_id:
            return False
        state = self.hass.states.get(self.entity_id)
        return state is not None and state.state == "on"

    def get_info(self) -> dict[str, Any]:
        """Get diagnostic information."""
        return {
            "type": "override",
            "entity_id": self.entity_id,
            "is_active": self.is_active(),
        }


class TriggerManager:
    """Manages multiple trigger handlers.
    
    This class coordinates multiple trigger handlers and provides a unified
    interface for the automation coordinator.
    
    To add a new trigger type:
    1. Create a class inheriting from TriggerHandler
    2. Implement required methods (async_setup, is_active, get_info)
    3. Add it to the manager with add_trigger()
    
    Example triggers you could add:
    - Door sensors (trigger on door open)
    - Presence detection (room occupancy)
    - Time-based schedules (active during certain hours)
    - Ambient light sensors (trigger only if dark)
    - Noise sensors (trigger on sound)
    """

    def __init__(self, hass: HomeAssistant):
        """Initialize the trigger manager."""
        self.hass = hass
        self._triggers: dict[str, TriggerHandler] = {}

    def add_trigger(self, name: str, trigger: TriggerHandler) -> None:
        """Add a trigger handler.
        
        Args:
            name: Unique name for this trigger
            trigger: TriggerHandler instance
        """
        if name in self._triggers:
            _LOGGER.warning("Replacing existing trigger '%s'", name)
            self._triggers[name].cleanup()
        
        self._triggers[name] = trigger
        _LOGGER.debug("Added trigger '%s' (%s)", name, type(trigger).__name__)

    async def async_setup_all(self) -> bool:
        """Set up all triggers.
        
        Returns:
            True if all triggers set up successfully
        """
        success = True
        for name, trigger in self._triggers.items():
            try:
                result = await trigger.async_setup()
                if not result:
                    _LOGGER.warning("Trigger '%s' setup returned False", name)
                    success = False
            except Exception as err:
                _LOGGER.error("Error setting up trigger '%s': %s", name, err)
                success = False
        
        return success

    def get_trigger(self, name: str) -> TriggerHandler | None:
        """Get a trigger by name."""
        return self._triggers.get(name)

    def is_trigger_active(self, name: str) -> bool:
        """Check if a specific trigger is active."""
        trigger = self._triggers.get(name)
        return trigger.is_active() if trigger else False

    def cleanup_all(self) -> None:
        """Clean up all triggers."""
        for trigger in self._triggers.values():
            trigger.cleanup()
        self._triggers.clear()

    def get_info(self) -> dict[str, Any]:
        """Get diagnostic information for all triggers."""
        return {
            "total_triggers": len(self._triggers),
            "triggers": {
                name: trigger.get_info()
                for name, trigger in self._triggers.items()
            },
        }
