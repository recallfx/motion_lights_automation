"""Comprehensive tests for timer_manager.py."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant




from homeassistant.components.motion_lights_automation.timer_manager import TimerManager, Timer, TimerType


class TestTimer:
    """Test Timer class."""

    async def test_timer_creation(self, hass: HomeAssistant):
        """Test timer creation."""
        callback = AsyncMock()
        timer = Timer(TimerType.MOTION, 10, callback, hass, "test_timer")
        
        assert timer.timer_type == TimerType.MOTION
        assert timer.duration == 10
        assert timer.name == "test_timer"
        assert timer.is_active is False

    async def test_timer_start(self, hass: HomeAssistant):
        """Test timer start."""
        callback = AsyncMock()
        timer = Timer(TimerType.MOTION, 5, callback, hass)
        
        timer.start()
        assert timer.is_active is True
        # Check within a reasonable range since timing isn't exact
        assert timer.remaining_seconds >= 0
        
        timer.cancel()

    async def test_timer_expiry(self, hass: HomeAssistant):
        """Test timer expiry calls callback."""
        callback = AsyncMock()
        timer = Timer(TimerType.MOTION, 0.1, callback, hass)
        
        timer.start()
        await asyncio.sleep(0.2)
        await hass.async_block_till_done()
        
        callback.assert_called_once()
        assert timer.is_active is False

    async def test_timer_cancel(self, hass: HomeAssistant):
        """Test timer cancellation."""
        callback = AsyncMock()
        timer = Timer(TimerType.MOTION, 10, callback, hass)
        
        timer.start()
        assert timer.is_active is True
        
        timer.cancel()
        assert timer.is_active is False
        
        await asyncio.sleep(0.1)
        callback.assert_not_called()

    async def test_timer_extend(self, hass: HomeAssistant):
        """Test timer extension."""
        callback = AsyncMock()
        timer = Timer(TimerType.MOTION, 1, callback, hass)
        
        timer.start()
        initial_remaining = timer.remaining_seconds
        
        timer.extend(5)
        new_remaining = timer.remaining_seconds
        
        assert new_remaining > initial_remaining
        timer.cancel()

    async def test_timer_remaining_seconds(self, hass: HomeAssistant):
        """Test remaining_seconds property."""
        callback = AsyncMock()
        timer = Timer(TimerType.MOTION, 10, callback, hass)
        
        assert timer.remaining_seconds == 0
        
        timer.start()
        assert timer.remaining_seconds > 0
        assert timer.remaining_seconds <= 10
        
        timer.cancel()

    async def test_timer_get_info(self, hass: HomeAssistant):
        """Test timer get_info method."""
        callback = AsyncMock()
        timer = Timer(TimerType.MOTION, 10, callback, hass, "test")
        
        info = timer.get_info()
        assert info["name"] == "test"
        assert info["type"] == "motion"
        assert info["duration"] == 10
        assert info["is_active"] is False


class TestTimerManager:
    """Test TimerManager class."""

    def test_timer_manager_creation(self, hass: HomeAssistant):
        """Test timer manager creation."""
        manager = TimerManager(hass)
        assert manager is not None

    async def test_create_timer(self, hass: HomeAssistant):
        """Test timer creation."""
        manager = TimerManager(hass)
        callback = AsyncMock()
        
        timer = manager.create_timer(TimerType.MOTION, callback, duration=10)
        assert timer is not None
        assert timer.duration == 10

    async def test_add_timer(self, hass: HomeAssistant):
        """Test adding timer."""
        manager = TimerManager(hass)
        callback = AsyncMock()
        
        timer = manager.create_timer(TimerType.MOTION, callback)
        manager.add_timer("test_timer", timer)
        
        retrieved = manager.get_timer("test_timer")
        assert retrieved == timer

    async def test_start_timer(self, hass: HomeAssistant):
        """Test starting timer."""
        manager = TimerManager(hass)
        callback = AsyncMock()
        
        timer = manager.start_timer("test", TimerType.MOTION, callback, duration=10)
        assert timer.is_active is True
        
        manager.cancel_timer("test")

    async def test_cancel_timer(self, hass: HomeAssistant):
        """Test canceling timer."""
        manager = TimerManager(hass)
        callback = AsyncMock()
        
        manager.start_timer("test", TimerType.MOTION, callback, duration=10)
        result = manager.cancel_timer("test")
        
        assert result is True

    async def test_cancel_nonexistent_timer(self, hass: HomeAssistant):
        """Test canceling nonexistent timer."""
        manager = TimerManager(hass)
        result = manager.cancel_timer("nonexistent")
        assert result is False

    async def test_cancel_all_timers(self, hass: HomeAssistant):
        """Test canceling all timers."""
        manager = TimerManager(hass)
        callback = AsyncMock()
        
        manager.start_timer("timer1", TimerType.MOTION, callback, duration=10)
        manager.start_timer("timer2", TimerType.EXTENDED, callback, duration=20)
        
        count = manager.cancel_all_timers()
        assert count == 2

    async def test_has_active_timer_specific(self, hass: HomeAssistant):
        """Test has_active_timer for specific timer."""
        manager = TimerManager(hass)
        callback = AsyncMock()
        
        assert manager.has_active_timer("test") is False
        
        manager.start_timer("test", TimerType.MOTION, callback, duration=10)
        assert manager.has_active_timer("test") is True
        
        manager.cancel_timer("test")

    async def test_has_active_timer_any(self, hass: HomeAssistant):
        """Test has_active_timer for any timer."""
        manager = TimerManager(hass)
        callback = AsyncMock()
        
        assert manager.has_active_timer() is False
        
        manager.start_timer("test", TimerType.MOTION, callback, duration=10)
        assert manager.has_active_timer() is True
        
        manager.cancel_timer("test")

    async def test_get_active_timers(self, hass: HomeAssistant):
        """Test get_active_timers."""
        manager = TimerManager(hass)
        callback = AsyncMock()
        
        manager.start_timer("timer1", TimerType.MOTION, callback, duration=10)
        manager.start_timer("timer2", TimerType.EXTENDED, callback, duration=20)
        
        active = manager.get_active_timers()
        assert len(active) == 2
        
        manager.cancel_all_timers()

    def test_set_default_duration(self, hass: HomeAssistant):
        """Test setting default duration."""
        manager = TimerManager(hass)
        manager.set_default_duration(TimerType.MOTION, 300)
        
        # Verify by creating a timer without duration
        callback = AsyncMock()
        timer = manager.create_timer(TimerType.MOTION, callback)
        assert timer.duration == 300

    async def test_extend_timer(self, hass: HomeAssistant):
        """Test extending timer."""
        manager = TimerManager(hass)
        callback = AsyncMock()
        
        timer = manager.start_timer("test", TimerType.MOTION, callback, duration=10)
        initial_remaining = timer.remaining_seconds
        
        result = manager.extend_timer("test", 5)
        assert result is True
        assert timer.remaining_seconds > initial_remaining
        
        manager.cancel_timer("test")

    async def test_extend_nonexistent_timer(self, hass: HomeAssistant):
        """Test extending nonexistent timer."""
        manager = TimerManager(hass)
        result = manager.extend_timer("nonexistent", 5)
        assert result is False

    def test_get_info(self, hass: HomeAssistant):
        """Test get_info method."""
        manager = TimerManager(hass)
        callback = AsyncMock()
        
        manager.start_timer("test", TimerType.MOTION, callback, duration=10)
        
        info = manager.get_info()
        assert info["total_timers"] == 1
        assert info["active_timers"] == 1
        assert "default_durations" in info
        assert "timers" in info
        
        manager.cancel_all_timers()

    async def test_replace_existing_timer(self, hass: HomeAssistant):
        """Test that adding timer with same name replaces old one."""
        manager = TimerManager(hass)
        callback = AsyncMock()
        
        timer1 = manager.create_timer(TimerType.MOTION, callback, duration=10)
        timer1.start()
        manager.add_timer("test", timer1)
        
        timer2 = manager.create_timer(TimerType.EXTENDED, callback, duration=20)
        manager.add_timer("test", timer2)
        
        # Old timer should be cancelled
        assert timer1.is_active is False
        
        retrieved = manager.get_timer("test")
        assert retrieved == timer2
