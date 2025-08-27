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

The integration uses a clear 6-state machine:

| State | Description | Timer Active |
|-------|-------------|--------------|
| `idle` | No lights on, no automation active | ❌ |
| `motion-auto` | Motion detected, automation in control | ❌ (motion cancels timers) |
| `motion-manual` | Motion detected, user modified lights | ❌ (timer deferred until motion off) |
| `auto` | Motion ended, automation lights on with timer | ✅ Motion timer (120s default) |
| `manual` | Motion ended, user lights on with timer | ✅ Extended timer (600s default) |
| `manual-off` | User turned lights off while in `auto`; temporary override blocking auto-on | ✅ Extended timer (600s default) |
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
- **Night Mode**: When optional dark outside entity is "on", uses night brightness level (default 10%)
- **Day Mode**: When dark outside entity is "off" or not configured, uses day brightness level (default 60%)
- **Day brightness = 0%**: Disables automatic motion activation during day hours
- **Dark Outside Entity**: Optional switch or binary sensor to determine night/day mode (if not configured, defaults to day mode)

### Light Integration
The integration controls three separate light entities (background, feature, ceiling lights) with intelligent brightness rules based on time of day. Future versions will simplify this to a single combined light entity.

## Configuration Options

| Setting | Description | Default |
|---------|-------------|---------|
| Motion Sensor | Binary sensor for motion detection | Required |
| Background Light | Light entity for background/accent lighting | Required |
| Feature Light | Light entity for feature/ambient lighting | Required |
| Ceiling Light | Light entity for main/overhead lighting | Required |
| Override Switch | Input boolean to disable automation | Required |
| Dark Outside Entity | Switch or binary sensor to determine night/day mode | Optional |
| Motion Activation | Enable/disable automatic light turn-on | `true` |
| No Motion Wait | Seconds before turning lights off after motion stops | `120` |
| Extended Timeout | Seconds before turning off manual lights | `600` |
| Day Brightness | Brightness percentage during day (0% = disabled) | `0` |
| Night Brightness | Brightness percentage during night | `1` |

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

The integration provides a comprehensive sensor entity exposing essential status and debugging information:

### Current Status
- **current_state**: Current state machine state (idle, motion-auto, motion-manual, auto, manual, manual-off, overridden)
- **motion_detected**: Real-time motion sensor status (true/false)
- **override_active**: Override switch status (true/false)

### Timer Information
- **timer_active**: Whether any timer is currently running (true/false)
- **time_until_action**: Seconds remaining until next automatic action (number or null)
- **next_action_time**: ISO timestamp of when next action will occur

### Debugging Information
- **manual_reason**: Explanation of why system is in manual state (most useful for troubleshooting)

### Configuration Info
- **motion_activation_enabled**: Current motion activation setting
- **day_brightness**: Configured day brightness percentage
- **night_brightness**: Configured night brightness percentage
- **no_motion_wait**: Motion timer duration in seconds
- **extended_timeout**: Extended timer duration in seconds

### Entity Assignments
- **motion_entity**: Motion sensor entity ID being monitored
- **background_light**: Background light entity ID being controlled
- **feature_light**: Feature light entity ID being controlled
- **ceiling_light**: Ceiling light entity ID being controlled
- **override_switch**: Override switch entity ID
- **dark_outside_entity**: Dark outside switch/binary sensor entity ID (optional)

### Statistics
- **motion_count**: Total motion events detected since startup
- **last_motion_time**: ISO timestamp of last motion detection

## Installation

1. Copy the `motion-lights-adv` folder to your `custom_components` directory
2. Restart Home Assistant
3. Go to Configuration → Integrations → Add Integration
4. Search for "Motion Lights Advanced" and configure

## Testing

Run all tests with coverage:
```bash
# From Home Assistant core directory
pytest tests/components/motion-lights-adv/ --cov=homeassistant.components.motion-lights-adv --cov-report=term-missing -v
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

The integration provides a refresh service for troubleshooting:
```yaml
service: motion-lights-adv.refresh_tracking
target:
  entity_id: sensor.motion_lights_study
```

## Technical Details

### Architecture
- **Event-driven**: Uses `async_track_state_change_event` for real-time responsiveness
- **Context tracking**: Distinguishes integration vs. external changes via Home Assistant context IDs
- **State machine**: Strict 7-state finite state machine for predictable behavior
- **Timer management**: Single active timer with proper cancellation and restart logic

### Performance
- **No polling**: Pure event-driven operation
- **Minimal overhead**: Only tracks configured entities
- **Async design**: Non-blocking integration with Home Assistant core

### Integration Quality
- **Config flow**: Full UI-based configuration
- **Translations**: Support for multiple languages
- **Diagnostics**: Comprehensive state information for troubleshooting
- **Services**: Refresh and debug services available

## Contributing

Contributions are welcome! Please ensure:

1. **Follow Home Assistant guidelines**: Use config flows, proper translations, async patterns
2. **Maintain test coverage**: Add tests for new functionality
3. **Update documentation**: Keep README and code comments current
4. **Preserve state machine**: Changes should fit within the existing 7-state model

### Development Setup
```bash
# Clone the repository
git clone https://github.com/recallfx/motion-lights-adv.git

# Set up development environment
cd motion-lights-adv
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install development dependencies
pip install homeassistant pytest pytest-cov

# Run tests
python test_logic.py
python -m pytest test_motion_coordinator.py -v
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Changelog

### v3.0.0 (Current)
- **🔧 Enhanced night/day detection**: Dark outside entity can now be either switch or binary sensor
- **📁 Repository restructure**: Renamed folder to `motion-lights-adv` for consistency
- **🎯 Improved flexibility**: Better support for various time-of-day detection methods
- **✅ Maintained all core functionality**: Same state machine and timer logic with three separate light entities
- **🧪 Verified through testing**: All logic tests pass with enhanced dark outside detection

**Migration from v2.x:**
- Update folder name from `motion_lights_adv` to `motion-lights-adv`
- Dark outside entity configuration now supports both switches and binary sensors
- All other settings and behavior remain the same

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

*For support, please check the [issues page](https://github.com/recallfx/motion-lights-adv/issues) or Home Assistant Community forums.*
