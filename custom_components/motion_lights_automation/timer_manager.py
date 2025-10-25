"""Timer management for motion lights automation.

This module provides flexible timer management that can be easily extended
with different timer strategies, multiple concurrent timers, etc.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class TimerType(Enum):
    """Types of timers supported."""

    MOTION = "motion"
    EXTENDED = "extended"
    CUSTOM = "custom"


class Timer:
    """Represents a single timer instance."""

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
        self.timer_type = timer_type
        self.duration = duration
        self.callback = callback
        self.hass = hass
        self.name = name or f"timer_{timer_type.value}"

        self._handle: asyncio.TimerHandle | None = None
        self._start_time: datetime | None = None
        self._end_time: datetime | None = None
        self._is_active = False

    def start(self) -> None:
        """Start or restart the timer."""
        if self._is_active:
            self.cancel()

        self._start_time = dt_util.now()
        self._end_time = self._start_time + timedelta(seconds=self.duration)
        self._is_active = True

        _LOGGER.debug(
            "Starting timer '%s' (%s) for %ds, will expire at %s",
            self.name,
            self.timer_type.value,
            self.duration,
            self._end_time.strftime("%H:%M:%S"),
        )

        self._handle = self.hass.loop.call_later(
            self.duration,
            lambda: self.hass.async_create_task(self._async_expire()),
        )

    async def _async_expire(self) -> None:
        """Handle timer expiration."""
        if not self._is_active:
            _LOGGER.debug("Timer '%s' expired but was already cancelled", self.name)
            return

        _LOGGER.info("Timer '%s' (%s) expired", self.name, self.timer_type.value)
        self._is_active = False
        self._handle = None

        try:
            await self.callback()
        except Exception as err:
            _LOGGER.error("Error in timer callback for '%s': %s", self.name, err)

    def cancel(self) -> None:
        """Cancel the timer."""
        if not self._is_active:
            return

        _LOGGER.debug("Cancelling timer '%s' (%s)", self.name, self.timer_type.value)

        if self._handle:
            self._handle.cancel()
            self._handle = None

        self._is_active = False
        self._start_time = None
        self._end_time = None

    def extend(self, additional_seconds: int) -> None:
        """Extend the timer by additional seconds."""
        if not self._is_active:
            _LOGGER.warning("Cannot extend inactive timer '%s'", self.name)
            return

        old_end = self._end_time
        new_duration = self.remaining_seconds + additional_seconds

        # Restart with new duration
        self.duration = new_duration
        self.start()

        _LOGGER.info(
            "Extended timer '%s' from %s to %s (+%ds)",
            self.name,
            old_end.strftime("%H:%M:%S") if old_end else "?",
            self._end_time.strftime("%H:%M:%S") if self._end_time else "?",
            additional_seconds,
        )

    @property
    def is_active(self) -> bool:
        """Check if timer is currently active."""
        return self._is_active

    @property
    def remaining_seconds(self) -> int:
        """Get remaining seconds (0 if not active)."""
        if not self._is_active or not self._end_time:
            return 0
        remaining = (self._end_time - dt_util.now()).total_seconds()
        return max(0, int(remaining))

    @property
    def end_time(self) -> datetime | None:
        """Get the time when timer will expire."""
        return self._end_time

    def get_info(self) -> dict[str, Any]:
        """Get timer diagnostic info."""
        return {
            "name": self.name,
            "type": self.timer_type.value,
            "duration": self.duration,
            "is_active": self._is_active,
            "remaining_seconds": self.remaining_seconds,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "end_time": self._end_time.isoformat() if self._end_time else None,
        }


class TimerManager:
    """Manages multiple timers for motion lights automation.

    This class provides a flexible timer management system that can handle
    multiple concurrent timers, different timer strategies, and easy extension.

    To add a new timer type:
    1. Add the timer type to TimerType enum
    2. Create the timer with create_timer() or use add_timer()
    3. The timer will automatically be tracked and managed

    To implement timer strategies (e.g., progressive timeout, adaptive timers):
    1. Create a new method that calculates duration based on context
    2. Use that duration when creating timers
    """

    def __init__(self, hass: HomeAssistant):
        """Initialize the timer manager."""
        self.hass = hass
        self._timers: dict[str, Timer] = {}
        self._default_durations: dict[TimerType, int] = {
            TimerType.MOTION: 120,
            TimerType.EXTENDED: 600,
        }

    def create_timer(
        self,
        timer_type: TimerType,
        callback: Callable,
        duration: int | None = None,
        name: str | None = None,
    ) -> Timer:
        """Create a new timer.

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
        timer = Timer(timer_type, duration, callback, self.hass, timer_name)

        return timer

    def add_timer(self, name: str, timer: Timer) -> None:
        """Add a timer to be managed.

        If a timer with the same name exists, it will be cancelled first.
        """
        if name in self._timers:
            self._timers[name].cancel()
        self._timers[name] = timer

    def start_timer(
        self,
        name: str,
        timer_type: TimerType,
        callback: Callable,
        duration: int | None = None,
    ) -> Timer:
        """Create and start a timer in one step.

        This is a convenience method that combines create_timer and add_timer.
        """
        timer = self.create_timer(timer_type, callback, duration, name)
        self.add_timer(name, timer)
        timer.start()
        return timer

    def cancel_timer(self, name: str) -> bool:
        """Cancel a specific timer by name.

        Returns:
            True if timer was cancelled, False if it didn't exist
        """
        timer = self._timers.get(name)
        if timer:
            timer.cancel()
            del self._timers[name]
            return True
        return False

    def cancel_all_timers(self) -> int:
        """Cancel all active timers.

        Returns:
            Number of timers cancelled
        """
        count = 0
        for timer in list(self._timers.values()):
            if timer.is_active:
                timer.cancel()
                count += 1
        self._timers.clear()
        _LOGGER.debug("Cancelled %d timer(s)", count)
        return count

    def get_timer(self, name: str) -> Timer | None:
        """Get a timer by name."""
        return self._timers.get(name)

    def has_active_timer(self, name: str | None = None) -> bool:
        """Check if a timer is active.

        Args:
            name: Timer name to check, or None to check if any timer is active
        """
        if name:
            timer = self._timers.get(name)
            return timer.is_active if timer else False

        return any(timer.is_active for timer in self._timers.values())

    def get_active_timers(self) -> list[Timer]:
        """Get all currently active timers."""
        return [timer for timer in self._timers.values() if timer.is_active]

    def set_default_duration(self, timer_type: TimerType, duration: int) -> None:
        """Set the default duration for a timer type."""
        self._default_durations[timer_type] = duration
        _LOGGER.debug(
            "Set default duration for %s timer to %ds",
            timer_type.value,
            duration,
        )

    def extend_timer(self, name: str, additional_seconds: int) -> bool:
        """Extend a timer by additional seconds.

        Returns:
            True if timer was extended, False if it doesn't exist
        """
        timer = self._timers.get(name)
        if timer and timer.is_active:
            timer.extend(additional_seconds)
            return True
        return False

    def get_info(self) -> dict[str, Any]:
        """Get timer manager diagnostic info."""
        return {
            "total_timers": len(self._timers),
            "active_timers": len(self.get_active_timers()),
            "default_durations": {
                timer_type.value: duration
                for timer_type, duration in self._default_durations.items()
            },
            "timers": {name: timer.get_info() for name, timer in self._timers.items()},
        }
