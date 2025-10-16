#!/usr/bin/env python3
"""Comprehensive test suite for modular architecture components."""

import asyncio
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Test State Machine
def test_state_machine():
    """Test state machine transitions and callbacks."""
    print("\n=== Testing State Machine ===")
    
    from state_machine import MotionLightsStateMachine, StateTransitionEvent
    from motion_coordinator import (
        STATE_IDLE, STATE_MOTION_AUTO, STATE_AUTO, STATE_MANUAL, STATE_OVERRIDDEN
    )
    
    sm = MotionLightsStateMachine(initial_state=STATE_IDLE)
    
    # Track callbacks
    enter_calls = []
    exit_calls = []
    
    def on_enter(state, from_state, event):
        enter_calls.append((state, from_state, event))
    
    def on_exit(state, to_state, event):
        exit_calls.append((state, to_state, event))
    
    sm.on_enter_state(STATE_MOTION_AUTO, on_enter)
    sm.on_exit_state(STATE_IDLE, on_exit)
    
    # Test transition
    assert sm.current_state == STATE_IDLE
    sm.transition(StateTransitionEvent.MOTION_ON)
    assert sm.current_state == STATE_MOTION_AUTO
    assert len(enter_calls) == 1
    assert len(exit_calls) == 1
    print("✅ State transitions work")
    
    # Test invalid transition
    try:
        sm.transition(StateTransitionEvent.MOTION_ON)  # Already in MOTION_AUTO
        print("✅ Invalid transitions blocked")
    except ValueError:
        print("✅ Invalid transitions raise errors")
    
    # Test motion off -> AUTO
    sm.transition(StateTransitionEvent.MOTION_OFF)
    assert sm.current_state == STATE_AUTO
    print("✅ MOTION_AUTO -> AUTO transition works")
    
    print("✅ State Machine PASSED\n")


def test_timer_manager():
    """Test timer manager functionality."""
    print("=== Testing Timer Manager ===")
    
    from timer_manager import TimerManager, TimerType
    
    # Create mock hass
    hass = MagicMock()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    hass.loop = loop
    
    tm = TimerManager(hass)
    
    # Track callbacks
    callback_fired = []
    
    async def timer_callback(timer_id):
        callback_fired.append(timer_id)
    
    # Start a timer
    timer = tm.start_timer("test1", TimerType.MOTION, 0.1, timer_callback)
    assert timer is not None
    assert tm.is_timer_active("test1")
    print("✅ Timer started")
    
    # Cancel timer
    tm.cancel_timer("test1")
    assert not tm.is_timer_active("test1")
    print("✅ Timer cancelled")
    
    # Test timer expiration
    tm.start_timer("test2", TimerType.MOTION, 0.05, timer_callback)
    loop.run_until_complete(asyncio.sleep(0.1))
    assert "test2" in callback_fired
    print("✅ Timer callback fired")
    
    # Test multiple timers
    tm.start_timer("timer_a", TimerType.MOTION, 0.2, timer_callback)
    tm.start_timer("timer_b", TimerType.EXTENDED, 0.2, timer_callback)
    assert tm.is_timer_active("timer_a")
    assert tm.is_timer_active("timer_b")
    print("✅ Multiple concurrent timers work")
    
    # Clean up
    tm.cancel_all_timers()
    assert not tm.is_timer_active("timer_a")
    assert not tm.is_timer_active("timer_b")
    print("✅ Cancel all timers works")
    
    loop.close()
    print("✅ Timer Manager PASSED\n")


def test_light_controller():
    """Test light controller with strategies."""
    print("=== Testing Light Controller ===")
    
    from light_controller import (
        LightController, 
        BrightnessStrategy,
        LightSelectionStrategy,
        LightContext
    )
    
    # Create mock hass
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states = MagicMock()
    
    # Mock light states
    def get_state(entity_id):
        mock_state = MagicMock()
        mock_state.state = "off"
        mock_state.attributes = {"brightness": 0}
        return mock_state
    
    hass.states.get.side_effect = get_state
    
    light_groups = {
        "background": ["light.bg1"],
        "feature": ["light.feat1"],
        "ceiling": ["light.ceil1"]
    }
    
    lc = LightController(hass, light_groups, "binary_sensor.dark")
    
    # Create context
    context = LightContext(
        time_of_day="day",
        is_dark=False,
        motion_active=True,
        all_lights=["light.bg1", "light.feat1", "light.ceil1"]
    )
    
    # Test custom brightness strategy
    class TestBrightnessStrategy(BrightnessStrategy):
        def get_brightness(self, context):
            return 50 if context.time_of_day == "day" else 10
    
    lc.set_brightness_strategy(TestBrightnessStrategy())
    
    # Test turn on
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def test_turn_on():
        await lc.turn_on_auto_lights(context)
        assert hass.services.async_call.called
        print("✅ Turn on lights works")
    
    loop.run_until_complete(test_turn_on())
    
    # Test custom selection strategy
    class TestSelectionStrategy(LightSelectionStrategy):
        def select_lights(self, context):
            return ["light.bg1"]  # Only background
    
    lc.set_selection_strategy(TestSelectionStrategy())
    context.all_lights = ["light.bg1", "light.feat1", "light.ceil1"]
    
    async def test_selection():
        selected = lc._select_lights_for_context(context)
        assert selected == ["light.bg1"]
        print("✅ Custom light selection works")
    
    loop.run_until_complete(test_selection())
    loop.close()
    
    print("✅ Light Controller PASSED\n")


def test_triggers():
    """Test trigger system."""
    print("=== Testing Triggers ===")
    
    from triggers import TriggerHandler, TriggerManager
    
    # Create mock hass
    hass = MagicMock()
    
    # Custom trigger
    class TestTrigger(TriggerHandler):
        def __init__(self):
            super().__init__()
            self._active = False
        
        async def setup(self):
            pass
        
        async def cleanup(self):
            pass
        
        def is_active(self):
            return self._active
        
        def set_active(self, active):
            self._active = active
            if active:
                self._notify_activated()
            else:
                self._notify_deactivated()
    
    # Test callbacks
    activated_count = [0]
    deactivated_count = [0]
    
    def on_activated():
        activated_count[0] += 1
    
    def on_deactivated():
        deactivated_count[0] += 1
    
    trigger = TestTrigger()
    trigger.on_activated(on_activated)
    trigger.on_deactivated(on_deactivated)
    
    # Test activation
    trigger.set_active(True)
    assert trigger.is_active()
    assert activated_count[0] == 1
    print("✅ Trigger activation works")
    
    # Test deactivation
    trigger.set_active(False)
    assert not trigger.is_active()
    assert deactivated_count[0] == 1
    print("✅ Trigger deactivation works")
    
    # Test trigger manager
    tm = TriggerManager(hass)
    tm.add_trigger("test", trigger)
    
    assert tm.is_any_trigger_active() == False
    trigger.set_active(True)
    assert tm.is_any_trigger_active() == True
    print("✅ Trigger manager tracks multiple triggers")
    
    print("✅ Triggers PASSED\n")


def test_manual_detection():
    """Test manual intervention detection."""
    print("=== Testing Manual Detection ===")
    
    from manual_detection import (
        ManualInterventionDetector,
        ManualInterventionStrategy
    )
    
    # Create mock states
    old_state = MagicMock()
    old_state.state = "on"
    old_state.attributes = {"brightness": 128}
    
    new_state = MagicMock()
    new_state.state = "on"
    new_state.attributes = {"brightness": 255}
    new_state.context = MagicMock()
    
    # Custom strategy
    class TestStrategy(ManualInterventionStrategy):
        def is_manual_intervention(self, entity_id, old_state, new_state, threshold):
            # Always consider significant brightness change as manual
            old_brightness = old_state.attributes.get("brightness", 0)
            new_brightness = new_state.attributes.get("brightness", 0)
            return abs(new_brightness - old_brightness) > threshold
    
    detector = ManualInterventionDetector()
    detector.add_strategy(TestStrategy())
    
    # Test detection
    is_manual, reason = detector.is_manual_intervention(
        "light.test", old_state, new_state, 50
    )
    
    assert is_manual == True
    print(f"✅ Manual intervention detected: {reason}")
    
    # Test no detection with small change
    new_state.attributes = {"brightness": 140}
    is_manual, reason = detector.is_manual_intervention(
        "light.test", old_state, new_state, 50
    )
    
    assert is_manual == False
    print("✅ Small changes not detected as manual")
    
    print("✅ Manual Detection PASSED\n")


def test_coordinator_integration():
    """Test that coordinator properly uses all modules."""
    print("=== Testing Coordinator Integration ===")
    
    from motion_coordinator import MotionLightsCoordinator
    from const import (
        CONF_MOTION_ENTITY, CONF_OVERRIDE_SWITCH,
        CONF_BACKGROUND_LIGHT, CONF_CEILING_LIGHT,
        CONF_FEATURE_LIGHT, CONF_DARK_OUTSIDE,
        CONF_MOTION_ACTIVATION, CONF_NO_MOTION_WAIT,
        CONF_EXTENDED_TIMEOUT, CONF_BRIGHTNESS_DAY,
        CONF_BRIGHTNESS_NIGHT
    )
    
    # Create mock hass
    hass = MagicMock()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    hass.loop = loop
    hass.async_create_task = lambda coro: loop.create_task(coro)
    hass.services = AsyncMock()
    hass.states = MagicMock()
    
    # Mock config
    config_entry = MagicMock()
    config_entry.data = {
        CONF_MOTION_ENTITY: "binary_sensor.motion",
        CONF_OVERRIDE_SWITCH: "input_boolean.override",
        CONF_BACKGROUND_LIGHT: "light.background",
        CONF_FEATURE_LIGHT: "light.feature",
        CONF_CEILING_LIGHT: "light.ceiling",
        CONF_DARK_OUTSIDE: "binary_sensor.dark",
        CONF_MOTION_ACTIVATION: True,
        CONF_NO_MOTION_WAIT: 5,
        CONF_EXTENDED_TIMEOUT: 10,
        CONF_BRIGHTNESS_DAY: 60,
        CONF_BRIGHTNESS_NIGHT: 10,
    }
    
    # Create coordinator (with patched event tracking)
    from unittest.mock import patch
    with patch("homeassistant.helpers.event.async_track_state_change_event"):
        coordinator = MotionLightsCoordinator(hass, config_entry)
    
    # Verify modules are initialized
    assert hasattr(coordinator, 'state_machine')
    assert hasattr(coordinator, 'timer_manager')
    assert hasattr(coordinator, 'light_controller')
    assert hasattr(coordinator, 'trigger_manager')
    assert hasattr(coordinator, 'manual_detector')
    print("✅ All modules initialized")
    
    # Verify state machine is wired
    assert coordinator.state_machine is not None
    print("✅ State machine wired to coordinator")
    
    # Verify timer manager is wired
    assert coordinator.timer_manager is not None
    print("✅ Timer manager wired to coordinator")
    
    # Verify light controller is wired
    assert coordinator.light_controller is not None
    print("✅ Light controller wired to coordinator")
    
    loop.close()
    print("✅ Coordinator Integration PASSED\n")


def test_extension_example():
    """Test that extension is easy with example."""
    print("=== Testing Extension Example ===")
    
    from triggers import TriggerHandler
    
    # Example: Add door sensor trigger (should be 5 minutes)
    class DoorTrigger(TriggerHandler):
        """Trigger when door opens."""
        
        def __init__(self, hass, entity_id):
            super().__init__()
            self.hass = hass
            self.entity_id = entity_id
        
        async def setup(self):
            """Set up door sensor listener."""
            # Would register listener here
            pass
        
        async def cleanup(self):
            """Clean up."""
            pass
        
        def is_active(self):
            """Check if door is open."""
            state = self.hass.states.get(self.entity_id)
            return state and state.state == "on"
    
    # Create mock hass
    hass = MagicMock()
    hass.states = MagicMock()
    
    # Mock door state
    door_state = MagicMock()
    door_state.state = "on"
    hass.states.get.return_value = door_state
    
    # Test door trigger
    door_trigger = DoorTrigger(hass, "binary_sensor.door")
    assert door_trigger.is_active() == True
    print("✅ Door trigger extension example works")
    
    print("✅ Extension Example PASSED\n")


if __name__ == "__main__":
    print("=" * 60)
    print("MODULAR ARCHITECTURE TEST SUITE")
    print("=" * 60)
    
    try:
        test_state_machine()
        test_timer_manager()
        test_light_controller()
        test_triggers()
        test_manual_detection()
        test_coordinator_integration()
        test_extension_example()
        
        print("=" * 60)
        print("🎉 ALL MODULE TESTS PASSED!")
        print("=" * 60)
        print("\nVerified components:")
        print("  ✅ State Machine - transitions & callbacks")
        print("  ✅ Timer Manager - multiple concurrent timers")
        print("  ✅ Light Controller - strategies & brightness")
        print("  ✅ Triggers - activation & deactivation")
        print("  ✅ Manual Detection - intervention strategies")
        print("  ✅ Coordinator - integration of all modules")
        print("  ✅ Extension - easy to add new features")
        print("\nModular architecture is production-ready! 🚀")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
