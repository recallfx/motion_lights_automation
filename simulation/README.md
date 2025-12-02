# Motion Lights Simulation

Standalone web-based simulator for testing motion lights automation logic without Home Assistant.

## Running

```bash
cd /path/to/motion_lights_automation
uv run python -m simulation.server
```

Open http://localhost:8092 in your browser.

## Features

- **Motion Sensors**: Click to simulate person entering/leaving a room
- **Lights**: Click to manually toggle (triggers manual intervention detection)
- **Override Switch**: Click to enable/disable automation override
- **Configuration Toggles**: Test different scenarios by toggling motion activation, house active, dark inside
- **Timer Display**: Watch motion and extended timers count down
- **Event Log**: Track state transitions in real-time

## State Machine

| State | Description |
|-------|-------------|
| `idle` | Lights off, waiting for motion |
| `motion-auto` | Motion detected, lights on (automation control) |
| `auto` | Motion cleared, motion timer running |
| `manual` | User adjusted lights, extended timer running |
| `motion-manual` | Motion active but user has control |
| `manual-off` | User turned off lights, blocking auto-on |
| `overridden` | Override switch active, automation disabled |

## Testing Scenarios

1. **Basic Motion Flow**: Click motion sensor → lights turn on → click sensor again → timer starts → lights turn off
2. **Manual Intervention**: While lights are on, click a light to toggle → state changes to MANUAL
3. **Override**: Click override switch → state changes to OVERRIDDEN, automation stops
4. **Motion Activation Disabled**: Toggle off "Motion Activation" → motion sensors won't turn on lights but will reset timers

## Files

- `server.py` - aiohttp web server with WebSocket
- `sim_coordinator.py` - State machine and timer logic (mirrors real coordinator)
- `static/index.html` - Single-page UI with inline CSS/JS
