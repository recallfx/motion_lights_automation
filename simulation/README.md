# Motion Lights Simulation

Web-based simulator for testing motion lights automation logic.

## Running

```bash
uv run motion-sim
```

Open http://localhost:8093 in your browser.

The simulation uses the **actual** `MotionLightsCoordinator` from the custom component with a real Home Assistant instance. This provides 100% behavior fidelity with production since it runs the exact same coordinator code.

## Features

- **Motion Sensors**: Click to simulate person entering/leaving a room
- **Lights**: Click to manually toggle (triggers manual intervention detection)
- **Brightness Controls**: +/- buttons to adjust light brightness manually
- **Override Switch**: Click to enable/disable automation override
- **Configuration Toggles**: Test different scenarios by toggling motion activation, house active, dark inside
- **Timer Display**: Watch motion and extended timers count down
- **Event Log**: Track state transitions in real-time
- **State Flow Diagram**: Visual representation of state transitions

## State Machine

| State | Description |
|-------|-------------|
| `standby` | Lights off, waiting for motion |
| `motion-detected` | Motion detected, lights on (automation control) |
| `auto-timeout` | Motion cleared, motion timer running |
| `manual-timeout` | User adjusted lights, extended timer running |
| `motion-adjusted` | Motion active but user has control |
| `manual-off` | User turned off lights, blocking auto-on |
| `disabled` | Override switch active, automation disabled |

## Testing Scenarios

1. **Basic Motion Flow**: Click motion sensor → lights turn on → click sensor again → timer starts → lights turn off
2. **Manual Intervention**: While lights are on, click a light to toggle → state changes to MANUAL
3. **Manual Brightness**: Use +/- buttons to adjust brightness → triggers manual state
4. **Manual Off**: Turn brightness to 0 → all lights off → state changes to MANUAL-OFF
5. **Override**: Click override switch → state changes to DISABLED, automation stops
6. **Motion Activation Disabled**: Toggle off "Motion Activation" → motion sensors won't turn on lights but will reset timers

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Browser UI                          │
│              (static/js/*, static/*.html)             │
└────────────────────────┬─────────────────────────────┘
                         │ WebSocket
┌────────────────────────▼─────────────────────────────┐
│              HASimulationServer                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │           HomeAssistant Instance                │ │
│  │  ┌───────────────────────────────────────────┐  │ │
│  │  │    MotionLightsCoordinator (REAL)         │  │ │
│  │  │  - state_machine                          │  │ │
│  │  │  - timer_manager                          │  │ │
│  │  │  - light_controller                       │  │ │
│  │  │  - manual_detector                        │  │ │
│  │  │  - triggers                               │  │ │
│  │  └───────────────────────────────────────────┘  │ │
│  │  Mock Services: light.turn_on/turn_off          │ │
│  │  Mock Entities: sensors, lights, switches       │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

## Files

- `ha_simulation.py` - Simulation server using real coordinator
- `static/index.html` - Dashboard HTML
- `static/js/` - Lit-based UI components
