# Architecture Guide

A modular, extensible architecture for motion-activated lighting automation in Home Assistant.

## System Overview

The integration uses a **modular architecture** with 5 specialized components orchestrated by a lightweight coordinator:

```
custom_components/motion_lights_automation/
├── motion_coordinator.py          ← Orchestrator (184 lines)
│
├── state_machine.py               ← State transitions & logic
├── timer_manager.py               ← Timer lifecycle management
├── light_controller.py            ← Light control with strategies
├── triggers.py                    ← Event trigger handlers
└── manual_detection.py            ← Manual intervention detection
```

## Design Philosophy

**Separation of Concerns:** Each module has a single, well-defined responsibility
**Strategy Pattern:** Pluggable strategies for brightness, light selection, and detection
**Event-Driven:** No polling, instant response to state changes
**Extensible:** Add features by implementing interfaces, not editing core logic

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│  motion_coordinator.py (Orchestrator)               │
│  • Initializes modules                              │
│  • Wires callbacks between components               │
│  • Delegates responsibilities                       │
└──────────────┬──────────────────────────────────────┘
               │
       ┌───────┴───────┐
       │               │
   ┌───▼───────┐   ┌───▼───────┐
   │   State   │   │  Timers   │
   │  Machine  │   │  Manager  │
   └───┬───────┘   └───────────┘
       │
   ┌───▼───────┐   ┌────────────┐
   │  Light    │   │  Triggers  │
   │ Controller│   │  Manager   │
   └───────────┘   └──────┬─────┘
                          │
                   ┌──────▼──────┐
                   │   Manual    │
                   │  Detection  │
                   └─────────────┘
```

Each component operates independently with clear interfaces between them.

## Module Responsibilities

| Module | Responsibility | Extension Point |
|--------|----------------|-----------------|
| `state_machine.py` | State transitions (IDLE → MOTION_AUTO → AUTO → etc) | Add states/transitions |
| `timer_manager.py` | Timer lifecycle (start/stop/extend) | Add timer types |
| `light_controller.py` | Light control with pluggable strategies | Implement `BrightnessStrategy` or `LightSelectionStrategy` |
| `triggers.py` | Event detection (motion, override, etc) | Implement `TriggerHandler` |
| `manual_detection.py` | Detect user interventions | Implement detection strategy |

## Extension Examples

### 1. Add Adaptive Brightness (5 min)
```python
class AdaptiveBrightnessStrategy(BrightnessStrategy):
    def get_brightness(self, context):
        hour = datetime.now().hour
        if 6 <= hour < 22:
            return 100  # Daytime: full brightness
        return 30       # Night: dim

# Use it:
light_controller.set_brightness_strategy(AdaptiveBrightnessStrategy())
```

### 2. Add Presence Detection (10 min)
```python
class PresenceTrigger(TriggerHandler):
    def is_active(self):
        return self.hass.states.get("binary_sensor.presence").state == "on"

trigger_manager.add_trigger("presence", PresenceTrigger(hass))
```

### 3. Add Scene Selection (5 min)
```python
class SceneSelectionStrategy(LightSelectionStrategy):
    def select_lights(self, context):
        if context.time_of_day == "night":
            return ["light.bedroom_path"]  # Only path lights
        return context.all_lights  # All lights during day

light_controller.set_selection_strategy(SceneSelectionStrategy())
```

### 4. Add Door Sensor Trigger (5 min)
```python
class DoorTrigger(TriggerHandler):
    def __init__(self, hass, entity_id):
        self.entity_id = entity_id

    async def setup(self):
        # Listen to door entity state changes
        pass

    def is_active(self):
        return self.hass.states.get(self.entity_id).state == "on"

# In coordinator:
self.trigger_manager.add_trigger("door", DoorTrigger(hass, "binary_sensor.door"))
```

## Key Design Patterns

### 1. Strategy Pattern
Used in `light_controller.py` for pluggable behavior:
- **BrightnessStrategy**: Determine brightness based on context
- **LightSelectionStrategy**: Select which lights to control

### 2. State Machine Pattern
Used in `state_machine.py` for predictable state transitions:
- 7 states: IDLE, MOTION_AUTO, MOTION_MANUAL, AUTO, MANUAL, MANUAL_OFF, OVERRIDDEN
- Clear transition rules
- State-specific callbacks

### 3. Observer Pattern
Used in coordinator for component communication:
- State machine notifies coordinator of state changes
- Coordinator updates sensors and triggers actions
- Loose coupling between components

### 4. Manager Pattern
Used in `timer_manager.py` and `triggers.py`:
- Centralized lifecycle management
- Clean setup/teardown
- Single point of control

## Component Interfaces

### State Machine
```python
class StateMachine:
    def transition_to(self, new_state: str, reason: str = None) -> None
    def get_current_state(self) -> str
    def set_callback(self, callback: Callable) -> None
```

### Timer Manager
```python
class TimerManager:
    async def start_motion_timer(self) -> None
    async def start_extended_timer(self) -> None
    def cancel_active_timer(self) -> None
    def is_timer_active(self) -> bool
```

### Light Controller
```python
class LightController:
    async def turn_on_lights(self, brightness: int) -> None
    async def turn_off_lights(self) -> None
    def set_brightness_strategy(self, strategy: BrightnessStrategy) -> None
    def set_selection_strategy(self, strategy: LightSelectionStrategy) -> None
```

### Trigger Manager
```python
class TriggerManager:
    def add_trigger(self, name: str, handler: TriggerHandler) -> None
    async def setup_all(self) -> None
    def cleanup_all(self) -> None
```

## Testing

```bash
# Run full test suite (213+ tests)
pytest tests/

# Run specific module tests
pytest tests/motion_lights_automation/test_state_machine.py
pytest tests/motion_lights_automation/test_light_controller.py

# Check coverage
pytest --cov=custom_components/motion_lights_automation tests/
```

**Test Coverage:** 213+ tests across all components
- State machine: 60+ tests
- Configuration flow: 45+ tests
- Light controller: 35+ tests
- Coordinator: 40+ tests
- Edge cases and error handling

## Best Practices

### Adding New Features
1. Identify which module handles the functionality
2. Implement the appropriate interface
3. Register with the coordinator
4. Add tests for the new functionality
5. Update documentation

### Modifying Existing Features
1. Locate the specific module (use Module Responsibilities table)
2. Modify only that module
3. Run tests to ensure no regressions
4. Update related tests if behavior changed

### Debugging
1. Enable debug logging for specific modules
2. Check state machine transitions in logs
3. Verify timer lifecycle events
4. Inspect sensor attributes for current state

## Further Reading

- `custom_components/motion_lights_automation/README.md` - Detailed user documentation
- Individual module docstrings - Implementation details
- `tests/` - Usage examples and edge cases
