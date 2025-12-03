# Testing Guide

## Running Tests

```bash
# Run all tests
uv run pytest tests/

# Run specific test file
uv run pytest tests/motion_lights_automation/test_state_machine.py -v

# Run specific test
uv run pytest tests/motion_lights_automation/test_state_machine.py::TestMotionLightsStateMachine::test_motion_on_from_idle -v

# Run with coverage
uv run pytest tests/ --cov=custom_components.motion_lights_automation

# Run with short traceback
uv run pytest tests/ --tb=short
```

Always use `uv run pytest`, not `pytest` directly. uv manages the virtual environment.

## Test Framework

Uses `pytest-homeassistant-custom-component` which provides:
- `hass` fixture - HomeAssistant instance
- `MockConfigEntry` - Config entry mock
- Async test support via `pytest-asyncio`
- Time manipulation via `pytest-freezer`

## Test File Structure

```
tests/
├── __init__.py
├── conftest.py                    # Shared fixtures
└── motion_lights_automation/
    ├── __init__.py
    ├── conftest.py                # Component-specific fixtures
    ├── test_state_machine.py      # Unit tests for state machine
    ├── test_timer_manager.py      # Unit tests for timers
    ├── test_triggers.py           # Unit tests for triggers
    ├── test_light_controller.py   # Unit tests for light control
    ├── test_manual_detection.py   # Unit tests for manual detection
    ├── test_config_flow.py        # Config flow tests
    ├── test_sensor.py             # Sensor entity tests
    ├── test_integration.py        # Full integration tests
    ├── test_scenarios.py          # Complex scenario tests
    └── test_*.py                  # Other test files
```

## Creating Config Entries

Use `MockConfigEntry` from the test framework:

```python
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.motion_lights_automation.const import DOMAIN

async def test_something(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Room",
        data={
            "lights": ["light.test"],
            "motion_sensors": ["binary_sensor.motion"],
        },
        options={
            "no_motion_wait": 300,
            "extended_timeout": 1200,
            "motion_activation": True,
        },
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
```

## Testing State Machine

```python
from custom_components.motion_lights_automation.state_machine import (
    MotionLightsStateMachine,
    StateTransitionEvent,
)
from custom_components.motion_lights_automation.const import (
    STATE_IDLE,
    STATE_MOTION_AUTO,
    STATE_AUTO,
)

def test_motion_cycle():
    sm = MotionLightsStateMachine()
    assert sm.current_state == STATE_IDLE

    # Motion on
    result = sm.transition(StateTransitionEvent.MOTION_ON)
    assert result is True
    assert sm.current_state == STATE_MOTION_AUTO

    # Motion off
    result = sm.transition(StateTransitionEvent.MOTION_OFF)
    assert result is True
    assert sm.current_state == STATE_AUTO
    assert sm.previous_state == STATE_MOTION_AUTO
```

## Testing Timers

```python
import asyncio
from unittest.mock import AsyncMock

from custom_components.motion_lights_automation.timer_manager import (
    Timer,
    TimerManager,
    TimerType,
)

async def test_timer_expiry(hass):
    callback = AsyncMock()
    manager = TimerManager(hass)

    timer = manager.start_timer(
        name="test",
        timer_type=TimerType.MOTION,
        callback=callback,
        duration=1,  # 1 second for fast test
    )

    assert timer.is_active
    await asyncio.sleep(1.5)

    callback.assert_called_once_with("test")
    assert not timer.is_active
```

## Testing with Mock Entities

The `motion_lights_automation_rig` provides mock entities:

```python
async def test_with_rig(hass):
    # Setup rig first
    rig_entry = MockConfigEntry(domain="motion_lights_automation_rig")
    rig_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(rig_entry.entry_id)
    await hass.async_block_till_done()

    # Now entities exist: light.test_light, binary_sensor.test_motion, etc.

    # Setup main component
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "lights": ["light.test_light"],
            "motion_sensors": ["binary_sensor.test_motion"],
        },
    )
    # ...
```

## Testing Coordinator

```python
async def test_coordinator_motion_cycle(hass, coordinator):
    """Test full motion detection cycle."""
    # Trigger motion on
    hass.states.async_set("binary_sensor.motion", "on")
    await hass.async_block_till_done()

    assert coordinator.state_machine.current_state == STATE_MOTION_AUTO

    # Trigger motion off
    hass.states.async_set("binary_sensor.motion", "off")
    await hass.async_block_till_done()

    assert coordinator.state_machine.current_state == STATE_AUTO
    assert coordinator.timer_manager.has_active_timer("motion")
```

## Cleanup Pattern

Always cleanup coordinators to prevent timer errors:

```python
import pytest

@pytest.fixture
async def coordinator(hass):
    """Create coordinator fixture with cleanup."""
    entry = MockConfigEntry(domain=DOMAIN, data={...})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coord = hass.data[DOMAIN][entry.entry_id]

    yield coord

    # Cleanup - IMPORTANT
    await coord.async_cleanup_listeners()
    await hass.config_entries.async_unload(entry.entry_id)
```

## Time Manipulation

Use `freezer` fixture for time-dependent tests:

```python
from datetime import timedelta

async def test_timer_with_frozen_time(hass, freezer):
    # Setup timer
    manager = TimerManager(hass)
    callback = AsyncMock()
    manager.start_timer("test", TimerType.MOTION, callback, duration=300)

    # Jump forward 5 minutes
    freezer.tick(timedelta(minutes=5))
    await hass.async_block_till_done()

    # Timer should have expired
    callback.assert_called_once()
```

## Testing Config Flow

```python
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

async def test_config_flow_basic(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Test Room",
            "lights": ["light.test"],
            "motion_sensors": ["binary_sensor.motion"],
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "advanced"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "no_motion_wait": 300,
            "extended_timeout": 1200,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
```

## Testing Sensors

```python
async def test_sensor_state(hass, coordinator):
    state = hass.states.get("sensor.test_room_motion_lights")

    assert state is not None
    assert state.state == "idle"
    assert state.attributes["previous_state"] is None
    assert "time_in_state" in state.attributes
```

## Common Test Patterns

### Async context manager for setup/teardown
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def setup_integration(hass, config):
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    try:
        yield hass.data[DOMAIN][entry.entry_id]
    finally:
        await hass.config_entries.async_unload(entry.entry_id)
```

### Waiting for state changes
```python
async def wait_for_state(hass, entity_id, target_state, timeout=5):
    """Wait for entity to reach target state."""
    import asyncio

    for _ in range(timeout * 10):
        state = hass.states.get(entity_id)
        if state and state.state == target_state:
            return True
        await asyncio.sleep(0.1)
    return False
```

### Mock callbacks
```python
from unittest.mock import AsyncMock, MagicMock, call

async def test_callbacks(hass):
    on_motion = AsyncMock()
    off_motion = AsyncMock()

    trigger = MotionTrigger(hass, config)
    trigger.on_motion_on(on_motion)
    trigger.on_motion_off(off_motion)

    # Trigger motion
    hass.states.async_set("binary_sensor.motion", "on")
    await hass.async_block_till_done()

    on_motion.assert_called_once()
    off_motion.assert_not_called()
```

## Debugging Tests

```bash
# Run with print output visible
uv run pytest tests/ -s

# Run with verbose logging
uv run pytest tests/ -v --log-cli-level=DEBUG

# Stop on first failure
uv run pytest tests/ -x

# Run last failed tests
uv run pytest tests/ --lf
```

## Common Pitfalls

- Don't forget `await hass.async_block_till_done()` after state changes
- Always cleanup coordinators to prevent "Timer was not cancelled" errors
- Use `MockConfigEntry` not custom dict for config entries
- Import from `custom_components.motion_lights_automation`, not `homeassistant.components`
- State machine tests don't need `hass` fixture - they're pure Python
- Timer tests need `hass` fixture for event loop access
