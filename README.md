# Motion Lights Advanced

A sophisticated Home Assistant custom integration providing intelligent motion-activated lighting with comprehensive manual override detection and automatic energy-saving features.

## Overview

Motion Lights Advanced provides a unified coordinator that manages both automatic motion lighting and manual light control with intelligent timeout management. The integration follows a strict state machine approach to ensure predictable behavior across all scenarios.

## Core Features

### ✅ Two Main Tasks
1. **Automatic Light ON**: Turn lights on automatically when motion is detected (respects motion activation setting and override switch)
2. **Automatic Light OFF**: Turn lights off automatically after configurable timeouts for energy saving (works even with motion activation disabled)

### ✅ Secondary Functions
- **Day/Night Brightness Control**: Automatically adjust brightness based on time of day
- **Manual Intervention Detection**: Detect when users manually adjust lights and extend timeouts appropriately
- **Override Protection**: Complete automation blocking when override switch is active

## State Machine

The integration uses a clear 7-state machine:

| State | Description | Timer Active |
|-------|-------------|--------------|
| `idle` | No lights on, no automation active | ❌ |
| `motion-auto` | Motion detected, automation in control | ❌ (motion cancels timers) |
| `motion-manual` | Motion detected, user modified lights | ❌ (timer deferred until motion off) |
| `auto` | Motion ended, automation lights on with timer | ✅ Motion timer (300s default) |
| `manual` | Motion ended, user lights on with timer | ✅ Extended timer (1200s default) |
| `manual-off` | User turned lights off while in `auto`; temporary override blocking auto-on | ✅ Extended timer (1200s default) |
| `overridden` | Override switch active, all automation blocked | ❌ |

## Behavior Details

### Motion Activation Enabled (Default)
1. **Motion ON** → Turn on appropriate lights → **MOTION-AUTO** state
2. **Motion OFF** from `motion-auto` → Start motion timer → **AUTO** state
3. **Timer expires** → Turn off lights → **IDLE** state
4. **Manual changes during motion** → **MOTION-MANUAL** (timer deferred until motion OFF)
5. **Manual changes during AUTO** → Cancel motion timer, start extended timer → **MANUAL** state
6. **User turns lights OFF during AUTO** → Cancel motion timer, start extended timer → **MANUAL-OFF** (blocks auto-on until timer expires)

### Motion Activation Disabled
- **Motion detection** → No automatic light changes, any existing lights marked as **MANUAL**
- **Manual light changes** → **MANUAL** state with extended timer for automatic turn-off
- **Timer expires** → Turn off lights → **IDLE** state

### Override Switch Behavior
- **Override ON** → Cancel all timers → **OVERRIDDEN** state (no automation)
- **Override OFF** → Evaluate current conditions and set appropriate state with timers

## Light Control Logic

### Time-Based Brightness
- Night Mode: When optional dark outside entity is "on", uses night brightness level (default 1%)
- Day Mode: When dark outside entity is "off" or not configured, uses day brightness level (default 30%)
- Day brightness = 0%: Disables automatic motion activation during day hours
- Dark Outside Entity: Optional switch or binary sensor to determine night/day mode (if not configured, defaults to day mode)

### Light Integration
The integration controls three separate light groups (background, feature, ceiling). You can assign multiple light entities to each group.

## Configuration Options

All fields in the UI are optional. Motion sensors and light groups support selecting multiple entities.

| Setting | Description | Default |
|---------|-------------|---------|
| Motion Sensor(s) | One or more binary_sensor.motion entities | None |
| Background Light(s) | One or more light entities for background/accent lighting | None |
| Feature Light(s) | One or more light entities for feature/ambient lighting | None |
| Ceiling Light(s) | One or more light entities for main/overhead lighting | None |
| Override Switch | A switch to disable all automation | None |
| Dark Outside Entity | Switch or binary_sensor to determine night/day | None |
| Motion Activation | Enable/disable automatic turn-on from motion | `true` |
| No Motion Wait | Seconds to wait after motion stops before auto-off | `300` |
| Extended Timeout | Seconds before turning off when in manual state | `1200` |
| Day Brightness | Brightness during day (0% disables auto-on) | `30` |
| Night Brightness | Brightness during night | `1` |

## Manual Intervention Detection

The integration detects manual changes as:
- **Light turned ON/OFF** by user or other automation
- **Brightness changes** greater than 2% threshold
- Any change **not** originating from this integration (tracked via Home Assistant context IDs)

### Manual Change Responses
- During **MOTION-AUTO** state: Switch to **MOTION-MANUAL**, defer timer until motion ends
- During **AUTO** state: Cancel motion timer, start extended timer, switch to **MANUAL**
- During **IDLE** state: Start extended timer, switch to **MANUAL**
- Motion activation disabled: Always start extended timer for any manual changes

## Energy Saving Features

### Automatic Turn-Off Scenarios
1. **Motion timer expires** (AUTO state) → Turn off motion-activated lights
2. **Extended timer expires** (MANUAL state) → Turn off manually controlled lights
3. **All lights turned off externally** → Return to IDLE state

### Timer Postponement
- **New motion during AUTO** → Cancel timer, return to MOTION-AUTO
- **New motion during MANUAL** → Cancel timer, return to MOTION-MANUAL
- **Manual changes during AUTO** → Switch to extended timer (MANUAL)
- **Manual OFF during AUTO** → Switch to extended timer (MANUAL-OFF), ignores motion until timer expires

## Sensor Data

The integration provides a sensor entity with essential status and debugging information:

### Current Status
- current_state: Current state (idle, motion-auto, motion-manual, auto, manual, manual-off, overridden)
- motion_detected: Real-time motion status (true/false)
- override_active: Override switch status (true/false)

### Timer Information
- timer_active: Whether a timer is running (true/false)
- time_until_action: Seconds remaining until next automatic action (number or null)
- next_action_time: ISO timestamp of when the next action will occur

### Debugging Information
- manual_reason: Why the system is in manual state (when applicable)

### Configuration Info
- motion_activation_enabled, day_brightness, night_brightness, no_motion_wait, extended_timeout

### Entity Assignments
- motion_entity, background_light, feature_light, ceiling_light, override_switch

### Simple Stats
- last_motion_time: ISO timestamp of last motion detection

## Installation

Requirements: Home Assistant 2024.12+ and Python 3.12+

1. Copy the `motion-lights-adv` folder to your `custom_components` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration
4. Search for "Motion Lights Advanced" and configure

## Testing

Run the repository tests:
```bash
pytest -q
```

## Troubleshooting

### Common Issues

**Lights not turning off automatically:**
- Check if motion activation is enabled in configuration
- Verify override switch is not active
- Check sensor entity for timer status and manual reason

**Motion not turning on lights:**
- Verify motion activation is enabled
- Check if override switch is active
- Ensure all light entities are properly configured
- Verify day brightness is > 0% if testing during day mode (when dark outside entity is off or not configured)

**Manual detection not working:**
- Verify all light entities are properly configured in the integration
- Check if changes are being made by other automations
- Review event log in sensor attributes

### Debug Logging

Add to `configuration.yaml`:
```yaml
logger:
  default: warning
  logs:
    custom_components.motion-lights-adv: debug
    custom_components.motion-lights-adv.motion_coordinator: debug
```

### Service Commands

The integration provides a refresh service for troubleshooting entity availability:
```yaml
service: motion_lights_adv.refresh_tracking
data:
  config_entry_id: "<your_config_entry_id>"
```
Tip: Find the config entry ID in Settings → Devices & Services → Motion Lights Advanced → three-dots menu.

## Technical Details

### Architecture
- Event-driven: Uses `async_track_state_change_event` for real-time responsiveness
- Context tracking: Distinguishes integration vs. external changes via Home Assistant context IDs
- State machine: Strict 7-state finite state machine for predictable behavior
- Timer management: Single active timer with proper cancellation and restart logic

### Performance
- No polling: Pure event-driven operation
- Minimal overhead: Only tracks configured entities
- Async design: Non-blocking integration with Home Assistant core

### Integration Quality
- Config flow: Full UI-based configuration (multi-entity selectors)
- Translations: Support for multiple languages
- Diagnostics: Comprehensive state information for troubleshooting
- Services: Refresh tracking service available

## Contributing

Contributions are welcome! Please ensure:

1. **Follow Home Assistant guidelines**: Use config flows, proper translations, async patterns
2. **Maintain test coverage**: Add tests for new functionality
3. **Update documentation**: Keep README and code comments current
4. **Preserve state machine**: Changes should fit within the existing 7-state model

### Development Setup
```bash
# Clone the repository
git clone https://github.com/recallfx/ha-motion-lights-adv.git

# Set up development environment (Python 3.12)
cd ha-motion-lights-adv
python3.12 -m venv .venv
source .venv/bin/activate

# Install dev dependencies
pip install "homeassistant>=2024.12.0" "pytest>=8.3.4" "pytest-cov" "ruff>=0.9.7" "pyyaml>=6.0.2"

# Run tests
pytest -q
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Changelog

### v3.1.0 (Current)
- Multi-entity support in the config flow (select multiple motion sensors and lights per group)
- Defaults updated: no_motion_wait=300s, extended_timeout=1200s, day_brightness=30%, night_brightness=1%
- Refresh service signature now requires config_entry_id
- Improved dark-outside handling (supports switch or binary_sensor)
- Docs and troubleshooting updates

Migration from v3.0.x:
- Update any automations calling the refresh service to use `motion_lights_adv.refresh_tracking` with `config_entry_id`

### v2.0.0
- **Unified coordinator**: Merged motion and manual coordinators into single state machine
- **Enhanced motion activation**: Separate control for auto-on vs auto-off behavior
- **Improved manual detection**: Better detection of external light changes
- **Comprehensive testing**: Full test suite for all functionality
- **Energy saving priority**: Lights turn off automatically even when motion activation disabled

### v1.x (Legacy)
- Initial release with separate motion and manual coordinators
- Basic motion detection and manual override
- Simple timeout management

---

*For support, please check the [issues page](https://github.com/recallfx/ha-motion-lights-adv/issues) or Home Assistant Community forums.*
