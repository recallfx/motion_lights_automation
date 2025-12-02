"""Timer management for motion lights automation.

This module provides Home Assistant-specific timer management that extends
the core BaseTimerManager with HA-specific scheduling.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Callable

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

# Re-export core classes for backward compatibility
from .core import (
    BaseTimer,
    BaseTimerManager,
    TimerType,
)

_LOGGER = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = [
    "Timer",
    "TimerManager",
    "TimerType",
]


class Timer(BaseTimer):
    """Home Assistant-specific timer implementation.

    Extends BaseTimer with HA event loop scheduling.
    """

    def __init__(
        self,
        timer_type: TimerType,
        duration: int,
        callback: Callable,
        hass: HomeAssistant,
        name: str | None = None,
    ):
        """Initialize a timer.

        Args:
            timer_type: Type of timer
            duration: Duration in seconds
            callback: Async callback to call when timer expires
            hass: HomeAssistant instance
            name: Optional name for debugging
        """
        super().__init__(timer_type, duration, callback, name)
        self.hass = hass
        self._handle: asyncio.TimerHandle | None = None

    def _get_current_time(self) -> datetime:
        """Get current time using Home Assistant utilities."""
        return dt_util.now()

    def start(self) -> None:
        """Start or restart the timer using HA event loop."""
        self._do_start()

        self._handle = self.hass.loop.call_later(
            self.duration,
            lambda: self.hass.async_create_task(self._async_expire()),
        )

    def cancel(self) -> None:
        """Cancel the timer."""
        if self._handle:
            self._handle.cancel()
            self._handle = None
        self._do_cancel()


class TimerManager(BaseTimerManager):
    """Home Assistant-specific timer manager.

    Extends BaseTimerManager with HA-specific timer creation.
    """

    def __init__(self, hass: HomeAssistant):
        """Initialize the timer manager."""
        super().__init__()
        self.hass = hass

    def create_timer(
        self,
        timer_type: TimerType,
        callback: Callable,
        duration: int | None = None,
        name: str | None = None,
    ) -> Timer:
        """Create a new Home Assistant timer.

        Args:
            timer_type: Type of timer to create
            callback: Async callback when timer expires
            duration: Duration in seconds (uses default if not specified)
            name: Optional name for the timer

        Returns:
            Created timer instance
        """
        if duration is None:
            duration = self._default_durations.get(timer_type, 300)

        timer_name = name or timer_type.value
        return Timer(timer_type, duration, callback, self.hass, timer_name)
