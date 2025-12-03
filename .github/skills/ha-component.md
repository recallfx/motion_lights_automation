# Home Assistant Component Development

## Architecture

This custom component uses a modular coordinator pattern with these core modules:

- `motion_coordinator.py` - Main coordinator that wires components together, delegates logic to specialized modules
- `state_machine.py` - State machine managing 7 states using `dt_util.now()` for HA time
- `timer_manager.py` - Timer management using HA event loop scheduling via `hass.loop.call_later()`
- `light_controller.py` - Controls lights with pluggable brightness/selection strategies
- `triggers.py` - Event handlers for motion sensors and override switches
- `manual_detection.py` - Detects manual light adjustments using context tracking
- `config_flow.py` - Two-step UI configuration (basic entities, advanced options)
- `sensor.py` - Diagnostic sensor exposing state machine info

## State Machine

Seven states with defined transitions:

| State | Description |
|-------|-------------|
| `standby` | No activity, lights off |
| `motion-detected` | Motion detected, lights auto-on |
| `auto-timeout` | Motion cleared, waiting for timeout |
| `manual-timeout` | User manually adjusted lights |
| `motion-adjusted` | Motion while in manual mode |
| `manual-off` | User manually turned off lights |
| `disabled` | Override switch active |

Legacy aliases exist for backward compatibility: `STATE_IDLE`, `STATE_MOTION_AUTO`, `STATE_AUTO`, etc.

Transition events: `MOTION_ON`, `MOTION_OFF`, `OVERRIDE_ON`, `OVERRIDE_OFF`, `MANUAL_INTERVENTION`, `MANUAL_OFF_INTERVENTION`, `TIMER_EXPIRED`, `LIGHTS_ALL_OFF`

## Timer System

Two primary timers:
- **MOTION timer** (`no_motion_wait`) - Short timeout after motion clears (default 5 min)
- **EXTENDED timer** (`extended_timeout`) - Long timeout for manual states (default 20 min)

```python
# Timer uses HA event loop
self._handle = self.hass.loop.call_later(
    self.duration,
    lambda: self.hass.async_create_task(self._async_expire()),
)
```

## Key Patterns

### Motion activation disabled behavior
When `motion_activation=False`, motion triggers still fire but coordinator resets extended timer without state transition. Prevents lights from timing out when room is actively used.

### Light context tracking
`LightController.is_integration_context()` distinguishes automation-triggered changes from manual interventions using HA context IDs.

### State transitions
Always use `StateTransitionEvent` enum values:
```python
self.state_machine.transition(StateTransitionEvent.MOTION_ON)
self.state_machine.transition(StateTransitionEvent.OVERRIDE_OFF, target_state=STATE_IDLE)
```

## Testing

```bash
uv run pytest tests/motion_lights_automation/ -v
```

Required test fixtures from `pytest-homeassistant-custom-component`:
- `hass` - HomeAssistant instance
- `MockConfigEntry` - Config entry mock

Always call `coordinator.async_cleanup_listeners()` in test teardown.

## Config Flow

Two-step flow:
1. **Basic setup** - Collects light entities, motion sensors, override switch
2. **Advanced setup** - Timeouts, brightness levels, motion activation toggle

Entity validation pattern:
```python
vol.All(cv.ensure_list, [cv.entity_id])  # For multi-entity fields
```

## File Organization

```
custom_components/motion_lights_automation/
├── __init__.py           # Platform setup
├── const.py              # Constants
├── motion_coordinator.py # Main coordinator
├── state_machine.py      # State machine with transitions
├── timer_manager.py      # Timer management
├── light_controller.py   # Light control strategies
├── triggers.py           # Motion/override triggers
├── manual_detection.py   # Manual intervention detection
├── config_flow.py        # UI configuration
├── sensor.py             # Diagnostic sensor
└── translations/
    └── en.json
```

## Extension Points

### New trigger type
```python
class CustomTrigger(TriggerHandler):
    async def async_setup(self) -> bool: ...
    def is_active(self) -> bool: ...
    def get_info(self) -> dict: ...

trigger_manager.add_trigger("custom", CustomTrigger(hass, config))
```

### New brightness strategy
```python
class CustomBrightnessStrategy(BrightnessStrategy):
    def get_brightness(self, context: dict) -> int:
        # context has is_house_active, is_dark_inside, motion_active
        return calculated_brightness

light_controller.set_brightness_strategy(CustomBrightnessStrategy())
```

### New manual detection strategy
```python
class CustomManualStrategy(ManualInterventionStrategy):
    def is_manual_intervention(self, event) -> tuple[bool, str]:
        return (is_manual, reason)
```

## Common Pitfalls

- Don't check `trigger.enabled` in motion handler - coordinator decides based on `motion_activation`
- Don't use `timer._start_time` (private) - use `timer.end_time` or `timer.remaining_seconds`
- Import from `custom_components.motion_lights_automation`, not `homeassistant.components.motion_lights_automation`
- State sensor updates via `coordinator.async_update_listeners()`, not direct `async_write_ha_state()`
- State strings use lowercase with hyphens: `STATE_MOTION_DETECTED = "motion-detected"`
