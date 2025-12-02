# Simulation Development

## Architecture

The simulation provides a standalone testing environment that uses the same core logic as the HA component:

```
simulation/
├── __init__.py
├── server.py           # FastAPI/Starlette web server with WebSocket
├── sim_coordinator.py  # Simulation coordinator using core module
└── static/
    └── index.html      # Industrial dashboard UI with Lit components
```

## Core Module Integration

The simulation imports shared logic from the HA component's core module:

```python
from custom_components.motion_lights_automation.core import (
    BaseStateMachine,
    BaseTimer,
    BaseTimerManager,
    StateTransitionEvent,
    TimerType,
    STATE_IDLE, STATE_AUTO, STATE_MANUAL, STATE_MANUAL_OFF,
    STATE_MOTION_AUTO, STATE_MOTION_MANUAL, STATE_OVERRIDDEN,
)
```

## SimMotionCoordinator

Extends core classes with asyncio-based timing:

```python
class SimTimer(BaseTimer):
    """Asyncio-based timer for simulation."""

    def _get_current_time(self) -> datetime:
        return datetime.fromtimestamp(time.time())

    def start(self) -> None:
        self._do_start()
        self._task = asyncio.create_task(self._timer_task())

    def cancel(self) -> None:
        self._do_cancel()
        if self._task:
            self._task.cancel()

class SimTimerManager(BaseTimerManager):
    """Timer manager using asyncio."""

    def create_timer(self, timer_type, callback, duration, name) -> BaseTimer:
        return SimTimer(timer_type, callback, duration, name)

class SimMotionCoordinator:
    """Uses BaseStateMachine directly for state transitions."""

    def __init__(self):
        self._state_machine = BaseStateMachine()
        self._timer_manager = SimTimerManager(on_timer_expired=self._on_timer_expired)
```

## WebSocket API

Real-time state updates via WebSocket at `/ws`:

```javascript
const ws = new WebSocket(`ws://${location.host}/ws`);
ws.onmessage = (event) => {
    const state = JSON.parse(event.data);
    // state.current_state, state.lights, state.sensors, state.timers, etc.
};
```

## REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/state` | GET | Current simulation state |
| `/api/sensor/{id}` | POST | Set sensor state `{state: bool}` |
| `/api/light/{id}` | POST | Set light state `{state: bool, brightness: int}` |
| `/api/config` | POST | Update config `{motion_activation, is_house_active, is_dark_inside}` |
| `/api/reset` | POST | Reset simulation to initial state |

## Running the Simulation

```bash
uv run python run_simulation.py
# Opens http://localhost:8092
```

## Industrial Dashboard UI

The UI uses vanilla HTML/CSS/JS with an industrial control panel aesthetic:

### CSS Variables
```css
:root {
    --bg-dark: #1a1a2e;
    --bg-card: #16213e;
    --accent: #0f3460;
    --highlight: #e94560;
    --text: #eee;
    --text-dim: #888;
    --success: #4ade80;
    --warning: #fbbf24;
}
```

### Flow Diagram Layout
```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
│   Motion    │────▶│   Coordinator   │────▶│    Light    │
│   Sensor    │     │   State Machine │     │   Output    │
└─────────────┘     └─────────────────┘     └─────────────┘
                           ▲
                    ┌──────┴──────┐
                    │   Override  │
                    │   Switch    │
                    └─────────────┘
```

### Component Structure

**Clickable input components** (Motion, Override):
```html
<div class="component-box clickable" data-entity="binary_sensor.motion">
    <div class="component-icon">◉</div>
    <div class="component-label">Motion</div>
    <div class="component-status">OFF</div>
</div>
```

**State display** with chip styling:
```html
<div class="state-chip" data-state="motion-auto">MOTION-AUTO</div>
```

**Timer progress bars**:
```html
<div class="timer-item">
    <span class="timer-name">motion</span>
    <div class="timer-bar">
        <div class="timer-progress" style="width: 75%"></div>
    </div>
    <span class="timer-remaining">3:45</span>
</div>
```

**Event log**:
```html
<div class="event-log">
    <div class="event-entry transition">State: idle → motion-auto</div>
    <div class="event-entry sensor">Motion: ON</div>
</div>
```

### State Chip Colors
```css
.state-chip[data-state="idle"] { background: var(--text-dim); }
.state-chip[data-state="motion-auto"] { background: var(--success); }
.state-chip[data-state="auto"] { background: #3b82f6; }
.state-chip[data-state="manual"] { background: var(--warning); }
.state-chip[data-state="manual-off"] { background: #f97316; }
.state-chip[data-state="motion-manual"] { background: #a855f7; }
.state-chip[data-state="overridden"] { background: var(--highlight); }
```

## Lit Components (Future)

When adding Lit web components:

```javascript
import { LitElement, html, css } from 'lit';

class MotionSensorComponent extends LitElement {
    static properties = {
        entityId: { type: String },
        state: { type: Boolean },
    };

    static styles = css`
        :host { display: block; }
        .component-box { /* ... */ }
    `;

    render() {
        return html`
            <div class="component-box ${this.state ? 'active' : ''}"
                 @click=${this._toggle}>
                <div class="component-icon">◉</div>
                <div class="component-label">Motion</div>
                <div class="component-status">${this.state ? 'ON' : 'OFF'}</div>
            </div>
        `;
    }

    async _toggle() {
        await fetch(`/api/sensor/${this.entityId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ state: !this.state }),
        });
    }
}
customElements.define('motion-sensor', MotionSensorComponent);
```

## SimConfig

Default configuration:
```python
@dataclass
class SimConfig:
    lights: list[str] = field(default_factory=lambda: ["light.room"])
    motion_sensors: list[str] = field(default_factory=lambda: ["binary_sensor.motion"])
    override_switch: str | None = "switch.override"
    no_motion_wait: int = 300      # 5 minutes
    extended_timeout: int = 1200   # 20 minutes
    motion_delay: int = 0
    motion_activation: bool = True
    brightness_active: int = 80
    brightness_inactive: int = 10
    is_house_active: bool = True
    is_dark_inside: bool = True
```

## Event Flow

1. User clicks Motion component → `POST /api/sensor/binary_sensor.motion`
2. Server calls `coordinator.process_sensor_event(entity_id, state)`
3. Coordinator triggers state machine transition
4. State machine logs: `State transition: idle -> motion-auto`
5. WebSocket broadcasts updated state to all clients
6. UI updates state chip, timers, event log

## Testing Simulation Code

```python
from simulation.sim_coordinator import SimMotionCoordinator, SimConfig
from custom_components.motion_lights_automation.core import STATE_IDLE, STATE_MOTION_AUTO

async def test_motion_activates_lights():
    coord = SimMotionCoordinator()
    assert coord._current_state == STATE_IDLE

    await coord.process_sensor_event('binary_sensor.motion', True)
    assert coord._current_state == STATE_MOTION_AUTO
```

## Debugging

Enable debug logging:
```python
import logging
logging.getLogger("simulation").setLevel(logging.DEBUG)
logging.getLogger("custom_components.motion_lights_automation.core").setLevel(logging.DEBUG)
```

State machine transitions are logged:
```
INFO:custom_components.motion_lights_automation.core.state_machine:State transition: idle -> motion-auto (event: motion_on)
INFO:simulation.sim_coordinator:State: idle → motion-auto (motion_on)
```
