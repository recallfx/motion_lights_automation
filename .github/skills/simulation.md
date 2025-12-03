# Simulation Development

## Architecture

The simulation uses a real Home Assistant instance with the actual `MotionLightsCoordinator`:

```
simulation/
├── __init__.py
├── ha_simulation.py    # HA-based simulation server
└── static/
    ├── index.html      # Industrial dashboard UI
    └── js/             # Lit web components
```

## HA-Based Simulation

The simulation runs the real coordinator inside a minimal HA instance:

```python
from homeassistant.core import HomeAssistant
from custom_components.motion_lights_automation import MotionLightsCoordinator

class HASimulationServer:
    async def _init_hass(self):
        self.hass = HomeAssistant("/tmp/ha_sim_config")
        await self.hass.async_start()

        # Register mock light services
        self._setup_mock_services()

        # Create real coordinator
        self.coordinator = MotionLightsCoordinator(self.hass, config_entry)
        await self.coordinator.async_setup_listeners()
```

Mock services preserve context to avoid false manual detection:
```python
async def mock_turn_on(call):
    for entity_id in call.data.get("entity_id", []):
        self.hass.states.async_set(
            entity_id, "on",
            {"brightness": call.data.get("brightness", 255)},
            context=call.context  # Preserve context!
        )
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
uv run motion-sim
# Opens http://localhost:8093
```

## Industrial Dashboard UI

The UI uses Lit web components with an industrial control panel aesthetic:

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

### State Chip Colors
```css
.state-chip[data-state="standby"] { background: var(--text-dim); }
.state-chip[data-state="motion-detected"] { background: var(--success); }
.state-chip[data-state="auto-timeout"] { background: #3b82f6; }
.state-chip[data-state="manual-timeout"] { background: var(--warning); }
.state-chip[data-state="manual-off"] { background: #f97316; }
.state-chip[data-state="motion-adjusted"] { background: #a855f7; }
.state-chip[data-state="disabled"] { background: var(--highlight); }
```

## Lit Components

Web components in `static/js/`:

```javascript
import { LitElement, html, css } from 'lit';

class FlowComponent extends LitElement {
    static properties = {
        state: { type: Object },
    };

    render() {
        return html`
            <div class="flow-diagram">
                <motion-box .active=${this.state?.motion}></motion-box>
                <state-display .state=${this.state?.current_state}></state-display>
                <light-output .brightness=${this.state?.brightness}></light-output>
            </div>
        `;
    }
}
```

## Event Flow

1. User clicks Motion component → `POST /api/sensor/binary_sensor.sim_motion`
2. Server sets entity state in HA → `hass.states.async_set()`
3. State change triggers coordinator's motion handler
4. Coordinator triggers state machine transition
5. WebSocket broadcasts updated state to all clients
6. UI updates state chip, timers, event log

## Debugging

Enable debug logging:
```python
import logging
logging.getLogger("simulation").setLevel(logging.DEBUG)
logging.getLogger("custom_components.motion_lights_automation").setLevel(logging.DEBUG)
```

State machine transitions are logged:
```
INFO:custom_components.motion_lights_automation.state_machine:State transition: standby -> motion-detected (event: motion_on)
```
