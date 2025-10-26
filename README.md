# Motion Lights Automation

**Intelligent motion-activated lighting with state machine control for Home Assistant**

Motion Lights Automation is a Home Assistant integration that provides sophisticated automatic lighting control based on motion detection, with support for manual interventions, override switches, and flexible brightness modes.

---

## ✨ Features

### Core Capabilities
- ✅ **Multi-sensor support** - Use multiple motion sensors for a single lighting zone
- ✅ **Three-tier lighting** - Ceiling, background, and feature lights with independent control
- ✅ **State machine** - 7 distinct states with intelligent transitions
- ✅ **Manual intervention detection** - Automatically detects and respects manual control
- ✅ **Override switch** - Temporarily disable automation without removing configuration
- ✅ **Dual timer system** - Motion timer + extended timer for flexible control
- ✅ **Active/Inactive brightness** - Different brightness levels based on house activity
- ✅ **House active switch** - Control brightness based on home occupancy/activity
- ✅ **Ambient light sensor** - Adjust brightness using boolean or lux sensors with hysteresis
- ✅ **Full UI configuration** - No YAML required

### Advanced Features
- 🎯 **Priority brightness logic** - house_active > ambient_light > default active mode
- 🔄 **Reconfiguration support** - Update settings without removing the integration
- 📊 **Status sensor** - Real-time monitoring of automation state
- ⚡ **Event-driven** - No polling, instant response to changes
- 🎨 **Modular architecture** - Extensible brightness and light selection strategies

---

## 📦 Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/recallfx/motion_lights_automation`
6. Select category: "Integration"
7. Click "Add"
8. Search for "Motion Lights Automation" and install
9. Restart Home Assistant
10. Go to **Settings** → **Devices & Services** → **Add Integration**
11. Search for "Motion Lights Automation"

### Manual Installation

1. Copy the `custom_components/motion_lights_automation` folder to your Home Assistant `custom_components` directory:
   ```
   <config>/custom_components/motion_lights_automation/
   ```

2. Restart Home Assistant

3. Go to **Settings** → **Devices & Services** → **Add Integration**

4. Search for "Motion Lights Automation" and click to add

---

## 🚀 Quick Start

### Basic Setup (Step 1)

Configure the essential entities:

| Field | Required | Description |
|-------|----------|-------------|
| **Name** | Yes | Friendly name for this automation (e.g., "Kitchen Motion Lights") |
| **Motion Sensors** | Yes | One or more motion sensors that trigger the lights |
| **Ceiling Lights** | No | Main overhead/ceiling lights |
| **Background Lights** | No | Ambient/background lighting |
| **Feature Lights** | No | Accent/feature lights |
| **Override Switch** | No | Switch to temporarily disable automation |
| **House Active Switch** | No | Switch indicating house is active (for brightness control) |
| **Ambient Light Sensor** | No | Binary sensor (e.g., sun) or lux sensor for ambient light detection |

**Note:** At least one light type (ceiling, background, or feature) must be configured.

### Advanced Settings (Step 2)

Fine-tune the behavior:

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| **Motion Activation** | Enabled | On/Off | Enable/disable motion detection |
| **Motion Delay** | 0s | 0-30s | Delay before turning on lights after motion detected |
| **No Motion Wait** | 300s | 0-3600s | Seconds to wait after motion stops before turning off |
| **Extended Timeout** | 1200s | 0-7200s | Additional time for manual/auto modes before returning to idle |
| **Brightness Active** | 80% | 0-100% | Brightness when house is active |
| **Brightness Inactive** | 10% | 0-100% | Brightness when house is inactive |
| **Ambient Light Threshold** | 50 lux | 10-500 lux | Threshold for lux sensors (only shown if lux sensor configured) |

---

## 🎯 How It Works

### State Machine

The integration operates through a 7-state machine:

```
┌─────────┐
│  IDLE   │ ← Lights off, no motion
└────┬────┘
     │ motion detected
     ↓
┌──────────────┐
│ MOTION_AUTO  │ ← Lights turned on automatically
└──┬────┬──────┘
   │    │ motion timer expires
   │    ↓
   │  ┌──────┐
   │  │ AUTO │ ← Motion timer active
   │  └──┬───┘
   │     │ timer expires
   │     ↓
   │  ┌─────┐
   │  │IDLE │
   │  └─────┘
   │
   │ manual intervention detected
   ↓
┌───────────────┐
│ MOTION_MANUAL │ ← Manual control during motion
└───────┬───────┘
        │ motion timer expires
        ↓
   ┌────────┐
   │ MANUAL │ ← Extended timer active
   └───┬────┘
       │ extended timer expires OR lights manually off
       ↓
   ┌─────────────┐
   │ MANUAL_OFF  │ ← User turned off lights
   └──────┬──────┘
          │ motion detected
          ↓
        ┌──────────────┐
        │ MOTION_AUTO  │
        └──────────────┘

┌─────────────┐
│ OVERRIDDEN  │ ← Override switch ON
└─────────────┘
```

### Brightness Logic

Priority system for determining brightness:

**Priority 1: House Active Switch** (if configured)
- Switch ON → Use `brightness_active` (default 80%)
- Switch OFF → Use `brightness_inactive` (default 10%)

**Priority 2: Ambient Light Sensor** (if configured and no house_active)
- **Binary sensor**: ON (dark) → Use `brightness_inactive`, OFF (bright) → Use `brightness_active`
- **Lux sensor**: Below LOW threshold → Use `brightness_inactive`, Above HIGH threshold → Use `brightness_active`
  - Uses hysteresis (±20 lux gap) to prevent flickering
  - Default 50 lux → LOW 30 lux, HIGH 70 lux
  - Maintains current brightness in dead zone (30-70 lux) for stability

**Priority 3: Default** (no switches configured)
- Always use `brightness_active`

### Use Case Example

In winter, it gets dark at 5 PM, but you want bright lights until bedtime (10 PM):
1. Add a `house_active` switch (e.g., `input_boolean.house_active`)
2. Create an automation to turn it OFF at 10 PM
3. Lights will be bright (80%) until 10 PM, then dim (10%) for nighttime movement

---

## 💡 Examples

### Example 1: Simple Bedroom

**Goal:** Turn on bedroom lights when motion detected, turn off after 5 minutes.

**Configuration:**
- Motion Sensors: `binary_sensor.bedroom_motion`
- Ceiling Lights: `light.bedroom_ceiling`
- No Motion Wait: `300` (5 minutes)
- Brightness Active: `80`
- Brightness Inactive: `20`

### Example 2: Kitchen with Day/Night Modes

**Goal:** Bright lights during the day, dim lights at night.

**Configuration:**
- Motion Sensors: `binary_sensor.kitchen_motion`
- Ceiling Lights: `light.kitchen_ceiling`
- Background Lights: `light.kitchen_under_cabinet`
- Ambient Light Sensor: `binary_sensor.sun_below_horizon`
- No Motion Wait: `300`
- Brightness Active: `100` (day mode)
- Brightness Inactive: `10` (night mode)

**How it works:**
- When sun is above horizon (sensor OFF), uses bright mode (100%)
- When sun is below horizon (sensor ON), uses dim mode (10%)

### Example 2a: Kitchen with Lux Sensor

**Goal:** Automatic brightness based on actual room brightness, preventing flickering.

**Configuration:**
- Motion Sensors: `binary_sensor.kitchen_motion`
- Ceiling Lights: `light.kitchen_ceiling`
- Background Lights: `light.kitchen_under_cabinet`
- Ambient Light Sensor: `sensor.kitchen_illuminance` (lux sensor)
- Ambient Light Threshold: `50` (lux)
- No Motion Wait: `300`
- Brightness Active: `100` (bright mode)
- Brightness Inactive: `10` (dim mode)

**How it works:**
- Below 30 lux → Dim mode (10%)
- 30-70 lux → Maintains current mode (hysteresis dead zone)
- Above 70 lux → Bright mode (100%)

**Why hysteresis?** Without it, the lights turning on would increase the lux reading, causing the mode to flip back and forth. The ±20 lux gap (40 lux total dead zone) prevents this flickering and also handles clouds passing, car headlights, or other transient light changes.

### Example 3: Living Room with House Active Mode

**Goal:** Bright lights when house is active, dim lights when winding down.

**Configuration:**
- Motion Sensors: `binary_sensor.living_room_motion`
- Ceiling Lights: `light.living_room_main`
- Background Lights: `light.living_room_lamp_1`, `light.living_room_lamp_2`
- Feature Lights: `light.living_room_accent`
- House Active: `input_boolean.house_active`
- No Motion Wait: `600` (10 minutes)
- Extended Timeout: `1800` (30 minutes)
- Brightness Active: `90`
- Brightness Inactive: `15`

**Helper Automations:**
```yaml
# Morning - House Active ON
automation:
  - alias: "House Active - Morning"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: input_boolean.turn_on
        target:
          entity_id: input_boolean.house_active

  # Evening - House Active OFF
  - alias: "House Active - Evening"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.house_active
```

### Example 4: Bathroom with Override

**Goal:** Auto lights normally, manual control when cleaning.

**Configuration:**
- Motion Sensors: `binary_sensor.bathroom_motion`
- Ceiling Lights: `light.bathroom_ceiling`
- Override Switch: `input_boolean.bathroom_override`
- No Motion Wait: `180` (3 minutes)
- Brightness Active: `100`

### Example 5: Sequential Lighting Flow

**Goal:** Create a natural progression of lighting as you move through connected spaces.

When you have an open floor plan or connected rooms, you can create a lighting flow that follows your movement. Configure each area with an increasing delay so lights activate in sequence, creating a welcoming path rather than everything turning on at once.

**Entryway Configuration (First to activate):**
- Motion Sensors: `binary_sensor.entryway_motion`
- Ceiling Lights: `light.entryway_ceiling`
- Motion Delay: `0` (activates immediately)
- No Motion Wait: `300`

**Hallway Configuration (Second):**
- Motion Sensors: `binary_sensor.hallway_motion`
- Ceiling Lights: `light.hallway_ceiling`
- Motion Delay: `2` (2-second delay)
- No Motion Wait: `300`

**Living Room Configuration (Third):**
- Motion Sensors: `binary_sensor.living_room_motion`
- Ceiling Lights: `light.living_room_ceiling`
- Motion Delay: `4` (4-second delay)
- No Motion Wait: `300`

**Result:** Coming home at night, lights activate progressively:
- Entryway → *2 seconds* → Hallway → *2 seconds* → Living Room

This creates a more natural, theater-like effect where the home "wakes up" sequentially rather than all at once.

---

## 📊 Status Sensor

The integration creates a sensor entity with comprehensive diagnostic information.

**Entity ID:** `sensor.<name>_lighting_automation`

**State Values:**
- `idle` - No motion, lights off
- `motion_auto` - Motion detected, lights on automatically
- `auto` - Automatic mode, extended timer running
- `motion_manual` - Manual intervention during motion
- `manual` - Manual mode, extended timer running
- `manual_off` - User manually turned off lights
- `overridden` - Override switch is ON

**Attributes:**
```yaml
current_state: auto
timer_active: true
time_until_action: 650
next_action_time: "2025-10-23T10:20:15"
motion_activation_enabled: true
brightness_active: 80
brightness_inactive: 10
current_brightness_mode: active
no_motion_wait: 300
extended_timeout: 1200
motion_entity: binary_sensor.kitchen_motion
ceiling_light: light.kitchen_ceiling
background_light: light.kitchen_under_cabinet
override_switch: input_boolean.kitchen_override
house_active_switch: input_boolean.house_active
ambient_light_sensor: binary_sensor.sun_below_horizon  # or sensor.kitchen_illuminance
ambient_light_threshold: 50  # only present for lux sensors
ambient_light_low: false  # true if below threshold or binary sensor ON
```

---

## 🔧 Troubleshooting

### Lights Don't Turn On with Motion

**Check:**
1. Motion sensor is working (verify in Developer Tools → States)
2. Motion activation is enabled (check advanced settings)
3. Override switch is OFF (if configured)
4. At least one light is configured
5. Check Home Assistant logs for errors

### Lights Turn Off Too Quickly/Slowly

**Solution:** Adjust **No Motion Wait** in advanced settings

### Manual Control Not Detected

**Check:**
1. Brightness changes are significant (>10%)
2. Lights are controlled via Home Assistant interface
3. Physical wall switches may not be detected (depends on integration)

**Workaround:** Use override switch for extended manual control

### Brightness Not Changing

**Check:**
1. House active switch or ambient light sensor is configured
2. Sensors are changing states correctly
3. Check sensor attributes for `current_brightness_mode` and `ambient_light_low`
4. For lux sensors, verify the sensor reports lux values (unit_of_measurement: "lx")

### Lux Sensor Flickering

**Problem:** Brightness keeps switching between active/inactive modes.

**Cause:** The lux sensor value is oscillating around the threshold.

**Solution:**
1. The integration includes ±20 lux hysteresis to prevent this
2. If still flickering, adjust the threshold away from typical values
3. Check if the lux sensor is too close to the lights (sensor should measure ambient light, not direct light from the controlled fixtures)
4. Consider using a binary sensor (e.g., sun below horizon) instead for simpler on/off behavior

### Debug Logging

Enable detailed logging in `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.motion_lights_automation: debug
```

---

## 🏗️ Architecture

### Modular Design

The integration uses a clean, modular architecture:

- **Coordinator** - Orchestrates all components
- **State Machine** - Manages state transitions
- **Timer Manager** - Handles motion and extended timers
- **Trigger Manager** - Manages event triggers (motion, override)
- **Light Controller** - Controls lights with pluggable strategies
- **Manual Detector** - Detects manual interventions

### Design Patterns

- **State Machine Pattern** - Clean state management
- **Strategy Pattern** - Pluggable brightness and light selection
- **Observer Pattern** - Coordinator listeners for state updates
- **Manager Pattern** - Timer and trigger management

### Quality


- ✅ Config flow
- ✅ Entity unique IDs
- ✅ Async setup
- ✅ Config entry unloading
- ✅ Entity unavailability handling
- ✅ Reconfiguration support
- ✅ Parallel updates

### Testing

Comprehensive test coverage with 226 tests covering state machine transitions, configuration flow, light controller behavior, coordinator logic, timer management, ambient light sensor detection with hysteresis, and edge cases.

Run tests:
```bash
uv run pytest tests/
```

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add/update tests
5. Submit a pull request

### Development Setup

```bash
# Clone the repository
git clone https://github.com/recallfx/motion_lights_automation.git
cd motion_lights_automation


# Install dependencies
uv sync

# Run tests
uv run pytest tests/

# Run linting
uv run ruff check .

# Format code
uv run ruff format .
```

---

## Changelog

### 5.2.0

Enhanced **Ambient Light Sensor** support with lux sensor capabilities. The dark_inside sensor field has been renamed to ambient_light_sensor and now supports both binary sensors (backward compatible) and lux sensors with intelligent hysteresis.

**New Features:**
- **Lux sensor support**: Use illuminance sensors (unit: lx) for ambient light detection
- **Automatic detection**: Integration auto-detects lux sensors vs binary sensors
- **Hysteresis algorithm**: ±20 lux gap prevents flickering from light feedback, clouds, or transients
- **Configurable threshold**: Set lux threshold (10-500, default 50) in advanced settings
- **Dead zone stability**: 40 lux dead zone maintains current brightness mode for stable operation

**Technical Details:**
- Default 50 lux threshold → LOW 30 lux, HIGH 70 lux
- Dim mode stays dim until lux > HIGH (70)
- Bright mode stays bright until lux < LOW (30)
- Invalid lux values safely fall back to dim mode

**Migration:** Existing configurations with dark_inside sensors will continue to work. The sensor field has been renamed but retains full backward compatibility for binary sensors.

### 5.1.0

Added **Motion Delay** feature for creating sequential lighting flows. Configure a 0-30 second delay before lights turn on after motion detection. This creates natural lighting progressions where lights activate in sequence as you move through connected spaces, rather than everything turning on simultaneously.

### 4.0.1

Motion sensors now reset the extended timer even when motion_activation is disabled. Previously, lights would turn off after the extended timeout regardless of ongoing motion detection. The fix ensures the MotionTrigger fires callbacks unconditionally, letting the coordinator decide how to handle them based on current state and settings.

### 4.0.0

Brightness control changed from day/night modes to an active/inactive system with priority-based selection. The coordinator delegates to five specialized modules instead of handling logic directly. Each module (state machine, timer manager, trigger manager, light controller, manual detector) can be extended through strategy patterns or base class inheritance.

### 3.1.0

Config flow fields accept multiple entities. The dark outside sensor connects to the brightness priority system. Default timeouts changed to better handle typical room occupancy patterns.

### 2.0.0

Coordinator handles all component initialization and event wiring. Manual intervention detection separates user actions from automation-triggered changes using Home Assistant context IDs.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙋 Support

- **Issues:** [GitHub Issues](https://github.com/recallfx/motion_lights_automation/issues)
- **Discussions:** [Home Assistant Community](https://community.home-assistant.io/)
- **Documentation:** See [ARCHITECTURE.md](custom_components/motion_lights_automation/ARCHITECTURE.md) for detailed technical documentation

---

## 👤 Author

**Marius Bieliauskas** ([@recallfx](https://github.com/recallfx))

---

## ⭐ Show Your Support

If this project helps you, please give it a ⭐️!

---

**Last Updated:** October 26, 2025
