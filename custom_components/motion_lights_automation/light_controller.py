"""Light control module for motion lights automation.

This module provides flexible light control with support for different
control strategies, brightness profiles, and easy extension.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from homeassistant.core import Context, HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass
class LightState:
    """Represents the state of a light."""

    entity_id: str
    is_on: bool
    brightness_pct: int = 0
    color_temp: int | None = None
    rgb_color: tuple[int, int, int] | None = None
    last_changed: float = 0.0

    @staticmethod
    def from_ha_state(entity_id: str, state) -> LightState:
        """Create LightState from a HomeAssistant state object."""
        is_on = state.state == "on"
        brightness = state.attributes.get("brightness", 0) or 0
        brightness_pct = int(brightness * 100 / 255) if brightness else 0

        return LightState(
            entity_id=entity_id,
            is_on=is_on,
            brightness_pct=brightness_pct,
            color_temp=state.attributes.get("color_temp"),
            rgb_color=state.attributes.get("rgb_color"),
        )


class BrightnessStrategy(ABC):
    """Abstract base class for brightness selection strategies.

    Implement this interface to create custom brightness strategies
    (e.g., based on time of day, ambient light sensors, user presence, etc.)
    """

    @abstractmethod
    def get_brightness(self, context: dict[str, Any]) -> int:
        """Get the target brightness percentage (0-100).

        Args:
            context: Dictionary containing contextual information like:
                - is_dark_inside: bool
                - ambient_light_level: int
                - room_occupancy: int
                - etc.

        Returns:
            Brightness percentage (0-100)
        """
        pass


class TimeOfDayBrightnessStrategy(BrightnessStrategy):
    """Default strategy that uses active/inactive brightness levels."""

    def __init__(self, active_brightness: int = 80, inactive_brightness: int = 10):
        """Initialize with active and inactive brightness levels."""
        self.active_brightness = active_brightness
        self.inactive_brightness = inactive_brightness

    def get_brightness(self, context: dict[str, Any]) -> int:
        """Get brightness based on ambient light and house activity level.

        Returns:
            0 if there's sufficient ambient light (bright mode)
            active_brightness if dark and house is active
            inactive_brightness if dark and house is inactive
        """
        # Check ambient light first - if it's bright outside, don't turn on lights
        is_dark_inside = context.get("is_dark_inside", True)
        if not is_dark_inside:
            # Bright mode - sufficient ambient light, no need for automation
            return 0

        # Dark mode - use house activity to decide brightness level
        is_house_active = context.get("is_house_active", True)
        return self.active_brightness if is_house_active else self.inactive_brightness


class LightController:
    """Controls lights with flexible strategies for brightness.

    This class provides a clean interface for light control that can be easily
    extended with different control strategies, transition effects, etc.

    To add a new brightness strategy:
    1. Create a class inheriting from BrightnessStrategy
    2. Implement get_brightness() method
    3. Set it with set_brightness_strategy()

    Future extensions could include:
    - Transition effects (fade in/out, color transitions)
    - Progressive lighting (turn on lights gradually)
    - Adaptive brightness (adjust based on ambient light)
    - Scene-based control
    """

    def __init__(
        self,
        hass: HomeAssistant,
        lights: list[str],
        brightness_strategy: BrightnessStrategy | None = None,
    ):
        """Initialize the light controller.

        Args:
            hass: HomeAssistant instance
            lights: List of light entity IDs to control
            brightness_strategy: Strategy for determining brightness
        """
        self.hass = hass
        self.lights = lights

        # Set default strategy if not provided
        self._brightness_strategy = brightness_strategy or TimeOfDayBrightnessStrategy()

        # Track light states
        self._light_states: dict[str, LightState] = {}
        self._context_tracking: set[str] = set()

    def set_brightness_strategy(self, strategy: BrightnessStrategy) -> None:
        """Set the brightness selection strategy."""
        self._brightness_strategy = strategy
        _LOGGER.debug("Updated brightness strategy to %s", type(strategy).__name__)

    def get_all_lights(self) -> list[str]:
        """Get all configured light entity IDs."""
        return list(self.lights)

    def update_light_state(self, entity_id: str, state) -> LightState:
        """Update tracked state for a light from HA state object."""
        light_state = LightState.from_ha_state(entity_id, state)
        self._light_states[entity_id] = light_state
        return light_state

    def get_light_state(self, entity_id: str) -> LightState | None:
        """Get tracked state for a light."""
        return self._light_states.get(entity_id)

    def any_lights_on(self) -> bool:
        """Check if any tracked lights are currently on."""
        return any(state.is_on for state in self._light_states.values())

    def refresh_all_states(self) -> None:
        """Refresh state tracking for all configured lights."""
        for light_id in self.get_all_lights():
            state = self.hass.states.get(light_id)
            if state:
                self.update_light_state(light_id, state)

    async def turn_on_auto_lights(self, context_data: dict[str, Any]) -> list[str]:
        """Turn on lights automatically based on brightness strategy.

        Args:
            context_data: Context for strategy (e.g., is_dark_inside, is_house_active)

        Returns:
            List of entity IDs that were turned on
        """
        # Determine brightness based on strategy
        target_brightness = self._brightness_strategy.get_brightness(context_data)

        if target_brightness <= 0:
            _LOGGER.debug("Brightness strategy returned 0, no lights will be turned on")
            return []

        # Turn on all configured lights
        turned_on = []
        for light_id in self.lights:
            current_state = self.hass.states.get(light_id)
            if not current_state:
                _LOGGER.warning("Light %s not found", light_id)
                continue

            # Skip if already on at correct brightness
            if current_state.state == "on":
                current_brightness = current_state.attributes.get("brightness", 0)
                current_brightness_pct = (
                    int(current_brightness * 100 / 255) if current_brightness else 0
                )
                if abs(current_brightness_pct - target_brightness) < 5:
                    _LOGGER.debug(
                        "Light %s already on at correct brightness (%d%%)",
                        light_id,
                        current_brightness_pct,
                    )
                    continue

            # Turn on the light
            if await self._async_set_light(light_id, "on", target_brightness):
                turned_on.append(light_id)

        if turned_on:
            _LOGGER.info(
                "Turned on %d light(s) at %d%% brightness",
                len(turned_on),
                target_brightness,
            )

        return turned_on

    async def turn_off_lights(self, light_ids: list[str] | None = None) -> list[str]:
        """Turn off specified lights (or all if not specified).

        Args:
            light_ids: List of light entity IDs, or None for all lights

        Returns:
            List of entity IDs that were turned off
        """
        if light_ids is None:
            light_ids = self.lights

        turned_off = []
        for light_id in light_ids:
            current_state = self.hass.states.get(light_id)
            if not current_state:
                continue

            # Skip if already off
            if current_state.state == "off":
                continue

            # Turn off the light
            if await self._async_set_light(light_id, "off", 0):
                turned_off.append(light_id)

        if turned_off:
            _LOGGER.info("Turned off %d light(s)", len(turned_off))

        return turned_off

    async def _async_set_light(
        self,
        entity_id: str,
        state: str,
        brightness_pct: int,
    ) -> bool:
        """Set a light's state.

        Returns:
            True if successful, False otherwise
        """
        try:
            service_data: dict[str, Any] = {"entity_id": entity_id}

            if state == "on" and brightness_pct > 0:
                service_data["brightness_pct"] = brightness_pct

            # Create context for tracking
            ctx = Context()
            self._context_tracking.add(ctx.id)

            # Call light service with 10-second timeout
            try:
                await asyncio.wait_for(
                    self.hass.services.async_call(
                        "light",
                        f"turn_{state}",
                        service_data,
                        context=ctx,
                    ),
                    timeout=10.0,
                )
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "Light service call timed out for %s (turn_%s)",
                    entity_id,
                    state,
                )
                return False

            _LOGGER.debug(
                "Set light %s to %s (brightness: %d%%)",
                entity_id,
                state,
                brightness_pct,
            )
            return True

        except Exception as err:
            _LOGGER.error("Error setting light %s: %s", entity_id, err)
            return False

    def is_integration_context(self, context: Context | None) -> bool:
        """Check if a context originated from this integration."""
        if not context:
            return False
        return context.id in self._context_tracking or (
            context.parent_id and context.parent_id in self._context_tracking
        )

    def cleanup_old_contexts(self, max_age_seconds: int = 30) -> None:
        """Remove old context IDs to prevent memory growth."""
        # In a real implementation, you'd track timestamps
        # For simplicity, we'll just limit the size
        if len(self._context_tracking) > 100:
            # Remove oldest half
            old_contexts = list(self._context_tracking)[:50]
            for ctx_id in old_contexts:
                self._context_tracking.discard(ctx_id)

    def get_info(self) -> dict[str, Any]:
        """Get diagnostic information."""
        return {
            "lights": list(self.lights),
            "total_lights": len(self.lights),
            "lights_on": sum(1 for state in self._light_states.values() if state.is_on),
            "brightness_strategy": type(self._brightness_strategy).__name__,
            "tracked_states": {
                entity_id: {
                    "is_on": state.is_on,
                    "brightness_pct": state.brightness_pct,
                }
                for entity_id, state in self._light_states.items()
            },
        }
