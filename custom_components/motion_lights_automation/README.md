# Motion Lights Automation - User Manual

**Complete documentation for the Motion Lights Automation integration**

This is the comprehensive user manual for Motion Lights Automation. For installation instructions and quick start, see the [main README](../../README.md).

---

## Table of Contents

- [Configuration Reference](#configuration-reference)
- [State Machine Explained](#state-machine-explained)
- [Brightness System](#brightness-system)
- [Timer System](#timer-system)
- [Manual Intervention Detection](#manual-intervention-detection)
- [Status Sensor Reference](#status-sensor-reference)
- [Use Cases & Examples](#use-cases--examples)
- [Troubleshooting Guide](#troubleshooting-guide)
- [Advanced Customization](#advanced-customization)
- [Integration with Other Systems](#integration-with-other-systems)
- [Migration Guides](#migration-guides)
- [FAQ](#faq)
- [Technical Architecture](#technical-architecture)

---

---

## Configuration Reference

### Basic Setup (Step 1)

The integration uses a two-step configuration process. In the first step, configure the essential entities:

| Field | Required | Description |
|-------|----------|-------------|
| **Name** | Yes | Friendly name for this automation (e.g., "Kitchen Motion Lights") |
| **Motion Sensors** | Yes | One or more motion sensors that trigger the lights |
| **Lights to Control** | Yes | The lights this automation should control |
| **Override Switch** | No | Switch to temporarily disable automation |
| **House Active Switch** | No | Switch indicating house is active (for brightness control) |
| **Ambient Light Sensor** | No | Sensor indicating ambient light level (lux sensor) or darkness (binary sensor or any sensor with binary state representation) |

**Note:** At least one light must be configured. Create separate instances if you need different behaviors for different light types.

### Advanced Settings (Step 2)

Fine-tune the behavior with advanced options:

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| **Motion Activation** | Enabled | On/Off | Enable/disable motion detection |
| **No Motion Wait** | 300s | 0-3600s | Seconds to wait after motion stops before turning off |
| **Extended Timeout** | 1200s | 0-7200s | Additional time for manual/auto modes before returning to idle |
| **Brightness Active** | 80% | 0-100% | Brightness when house is active |
| **Brightness Inactive** | 10% | 0-100% | Brightness when house is inactive |

---

## State Machine Explained

Understanding the state machine is key to understanding how Motion Lights Automation behaves.

### The 7 States

The integration operates through a finite state machine with 7 distinct states. Each state represents a specific scenario in the light automation lifecycle:

```
┌─────────┐
│  IDLE   │ ← Lights off, no motion
└────┬────┘
     │ motion detected
     ↓
┌──────────────┐
│ MOTION_AUTO  │ ← Lights turned on automatically
└──┬────┬──────┘
   │    │ motion timer expires (no motion for N seconds)
   │    ↓
   │  ┌──────┐
   │  │ AUTO │ ← Automatic mode, motion timer active (waiting for more motion)
   │  └──┬───┘
   │     │ motion timer expires (no further motion) OR all lights manually off
   │     ↓
   │  ┌─────┐
   │  │IDLE │
   │  └─────┘
   │
   │ manual intervention detected
   ↓
┌───────────────┐
│ MOTION_MANUAL │ ← Manual control detected during motion
└───────┬───────┘
        │ motion timer expires
        ↓
   ┌────────┐
   │ MANUAL │ ← Manual mode, extended timer active
   └───┬────┘
       │ extended timer expires OR all lights manually off
       ↓
   ┌─────────────┐
   │ MANUAL_OFF  │ ← User manually turned off lights
   └──────┬──────┘
          │ motion detected (if activation enabled)
          ↓
        ┌──────────────┐
        │ MOTION_AUTO  │
        └──────────────┘

┌─────────────┐
│ OVERRIDDEN  │ ← Override switch is ON (automation disabled)
└─────────────┘
```

### State Transition Rules

| Current State | Trigger | Next State | Action |
|---------------|---------|------------|--------|
| IDLE | Motion detected + activation enabled | MOTION_AUTO | Turn on lights at calculated brightness |
| IDLE | Override switch ON | OVERRIDDEN | Do nothing |
| MOTION_AUTO | Motion stops | AUTO | Start motion timer |
| MOTION_AUTO | Manual intervention | MOTION_MANUAL | Respect manual settings |
| MOTION_AUTO | Override switch ON | OVERRIDDEN | Cancel all timers |
| AUTO | Motion timer expires | IDLE | Turn off lights |
| AUTO | Motion detected again | MOTION_AUTO | Cancel timer, keep lights on |
| AUTO | Manual intervention | MANUAL | Switch to extended timer |
| AUTO | All lights manually turned off | MANUAL_OFF | Switch to extended timer, block auto-on |
| MANUAL | Extended timer expires | IDLE | Turn off lights |
| MANUAL | All lights manually turned off | MANUAL_OFF | Block auto-on until timer expires |
| MANUAL_OFF | Extended timer expires | IDLE | Re-enable automation |
| MOTION_MANUAL | Motion stops | MANUAL | Start extended timer |
| OVERRIDDEN | Override switch OFF | Evaluate current state | Transition to appropriate state |
| ANY | Override switch ON | OVERRIDDEN | Cancel all timers, disable automation |

### When Lights Actually Turn On/Off

**Lights Turn ON:**
- State: IDLE → MOTION_AUTO (motion detected, activation enabled)
- Brightness: Calculated using priority system (see Brightness System section)
- Lights: All configured lights or strategy-selected subset

**Lights Turn OFF:**
- State: AUTO → IDLE (motion timer expired)
- State: MANUAL → IDLE (extended timer expired)
- All lights turn off together

**Lights Stay As-Is:**
- MOTION_MANUAL: Respects your manual settings
- MANUAL: Respects your manual settings
- MANUAL_OFF: Keeps lights off until timer expires
- OVERRIDDEN: No automation control

---

## Brightness System

The integration determines brightness using a priority system:

**Priority 1: House Active Switch** (if configured)
- Switch ON → Use `brightness_active` (default 80%)
- Switch OFF → Use `brightness_inactive` (default 10%)

**Priority 2: Ambient Light Sensor** (if configured and no house_active)
- Room bright → Use `brightness_active` (lights may not turn on if brightness is 0)
- Room dark → Use `brightness_inactive`

**Priority 3: Default** (no switches configured)
- Always use `brightness_active`

### Important: Brightness Zero Behavior

When the brightness strategy returns 0% (e.g., ambient light sensor shows the room is already bright), **the lights will not turn on**. This prevents unnecessary light usage when there's sufficient ambient light.

### Brightness Calculation Examples

**Scenario 1: Only `ambient_light_sensor` configured**
```yaml
ambient_light_sensor: binary_sensor.room_dark
brightness_active: 90
brightness_inactive: 15
```
**Behavior:**
- Room bright (sensor OFF) → Brightness 0% (lights don't turn on)
- Room dark (sensor ON) → 15% brightness

**Use Case:** Windowless bathroom - lights only turn on when room is dark

**Scenario 2: Only `house_active` configured**
```yaml
house_active: input_boolean.house_active
brightness_active: 80
brightness_inactive: 10
```
**Behavior:**
- House active ON → 80% brightness
- House active OFF → 10% brightness

**Use Case:** Daytime full brightness, nighttime dim brightness

**Scenario 3: Both configured (house_active takes priority)**
```yaml
house_active: input_boolean.house_active
ambient_light_sensor: binary_sensor.room_dark
brightness_active: 100
brightness_inactive: 20
```
**Behavior (house_active takes priority for brightness):**
- House active ON → 100% brightness
- House active OFF → 20% brightness

**Note:** When both are configured, the house_active switch controls brightness. The ambient_light_sensor can still prevent lights from turning on if the room is bright.

**Scenario 4: Neither configured**
```yaml
brightness_active: 75
brightness_inactive: 5
```
- Always uses `brightness_active` (75%)
- All lights always turn on
- `brightness_inactive` is never used

### Real-World Brightness Use Case

**Problem:** You want full lighting during active hours (7 AM - 10 PM), but only dim lights at night for bathroom trips.

**Solution:**
1. Create `input_boolean.house_active` helper
2. Configure integration with:
   - `house_active: input_boolean.house_active`
   - `lights: light.bathroom_main, light.bathroom_night_light`
   - `brightness_active: 80`
   - `brightness_inactive: 5`
3. Create two automations:
   ```yaml
   # Morning: Enable house active
   - alias: "House Active - Morning"
     trigger:
       - platform: time
         at: "07:00:00"
     action:
       - service: input_boolean.turn_on
         target:
           entity_id: input_boolean.house_active

   # Bedtime: Disable house active
   - alias: "House Active - Bedtime"
     trigger:
       - platform: time
         at: "22:00:00"
     action:
       - service: input_boolean.turn_off
         target:
           entity_id: input_boolean.house_active
   ```

**Result:**
- **7 AM - 10 PM (house active ON):** All lights at 80% when motion detected
- **10 PM - 7 AM (house inactive):** All lights at 5% when motion detected

**Why `ambient_light_sensor` is useful:**
- Works for windowless rooms (bathrooms, closets, hallways)
- Can use lux sensor to detect actual room brightness
- Prevents lights from turning on when there's sufficient ambient light

---

## Timer System

The integration uses two types of timers with different purposes.

### Motion Timer

**Purpose:** Wait for motion to stop before starting the "turn off" countdown

**Default Duration:** 300 seconds (5 minutes)

**When It Starts:**
- State transition: MOTION_AUTO → AUTO (motion stops)

**What It Does:**
- Gives you time to move around without lights turning off
- Resets if motion detected again (AUTO → MOTION_AUTO)
- If expires: Turn off lights and transition to IDLE

**Configuration:** Set via "No Motion Wait" in advanced settings (0-3600 seconds)

**Example:** You set "No Motion Wait" to 180 seconds (3 minutes)
1. Motion detected at 10:00:00 → Lights turn on (MOTION_AUTO)
2. Motion stops at 10:02:00 → Timer starts (AUTO state)
3. If no more motion by 10:05:00 → Lights turn off (IDLE state)
4. But if motion detected at 10:04:00 → Timer canceled, back to MOTION_AUTO

### Extended Timer

**Purpose:** Give manual control plenty of time before automation resumes

**Default Duration:** 1200 seconds (20 minutes)

**When It Starts:**
- Manual intervention detected during AUTO → MANUAL
- User turns off lights during AUTO → MANUAL_OFF
- Motion stops during MOTION_MANUAL → MANUAL

**What It Does:**
- Respects that you took manual control
- Gives you extended time before automation resumes
- If expires: Turn off lights (if still on) and return to IDLE

**Configuration:** Set via "Extended Timeout" in advanced settings (0-7200 seconds)

**Example:** You manually dim lights, extended timeout is 1200 seconds (20 minutes)
1. Lights auto-on at 100% (MOTION_AUTO)
2. You manually dim to 30% → Extended timer starts (MANUAL)
3. Motion stops → Timer continues running
4. After 20 minutes of no interaction → Lights turn off (IDLE)

### Timer Behavior Comparison

| Timer | Duration | Starts When | Purpose | Reset By |
|-------|----------|-------------|---------|----------|
| Motion | 300s default | Motion stops | Wait before auto-off | New motion |
| Extended | 1200s default | Manual intervention | Respect manual control | Not reset |

---

## Manual Intervention Detection

The integration detects manual interventions in two ways:

1. **Brightness Change**: User adjusted brightness significantly (>10%)
2. **Time-based**: User turned lights on/off manually (detected via context tracking)

When manual intervention is detected:
- State transitions to MOTION_MANUAL (if during motion) or MANUAL (if after)
- Automation respects your manual settings
- Extended timer starts (or continues)
- Eventually returns to automatic mode after timer expires

### Context Tracking

The integration uses Home Assistant's **context** system to distinguish its own actions from external changes:

**Integration Actions** (not manual):
- Have a specific context ID created by the integration
- Are ignored by manual detection system

**External Actions** (manual):
- Have different context IDs (user, other automations, etc.)
- Trigger manual intervention detection

**What This Means:**
- The integration won't detect its own automated changes as "manual"
- Changes from physical switches, apps, or other automations are detected
- Voice assistants (Alexa, Google) are detected as manual

### Manual Detection Limitations

**Will Detect:**
- ✅ Changes via Home Assistant UI/app
- ✅ Changes via voice assistants
- ✅ Changes from other automations
- ✅ Significant brightness adjustments (>10%)
- ✅ Lights turned on/off externally

**May Not Detect:**
- ❌ Physical wall switches (depends on how the light reports state)
- ❌ Very small brightness changes (<10%)
- ❌ Changes that don't update entity state in HA

**Workaround:** Use the override switch for guaranteed manual control

---

## Status Sensor Reference

Every integration instance creates a sensor entity for monitoring and diagnostics.

### Sensor Entity

**Entity ID Format:** `sensor.<configured_name>_lighting_automation`

**Example:** If you named your integration "Kitchen", the sensor will be `sensor.kitchen_lighting_automation`

### State Values

The sensor's state shows the last human-readable event message (e.g., "Lights turned on by motion", "Lights turned off (timeout)"). The `current_state` attribute reflects the state machine state:

| State Value | Meaning | Typical Duration |
|-------------|---------|------------------|
| `idle` | No automation active, lights off | Until motion detected |
| `motion-auto` | Motion active, lights on by automation | While motion continues |
| `auto` | Motion ended, motion timer counting down | 5 minutes (default) |
| `motion-manual` | Motion active, manual control detected | While motion continues |
| `manual` | Manual control, extended timer counting | 20 minutes (default) |
| `manual-off` | User turned off lights, blocking auto-on | 20 minutes (default) |
| `overridden` | Override switch active, automation disabled | While override ON |

### Sensor Attributes

Complete list of available attributes:

#### Current State & Conditions
```yaml
current_state: "auto"                    # Current state machine state
motion_active: false                     # Current motion sensor state
is_dark_inside: true                     # Current ambient light condition
is_house_active: false                   # Current house_active switch state
motion_activation_enabled: true          # Is motion activation enabled?
```

#### State Transitions
```yaml
last_transition_reason: "motion_off"     # Event that triggered last transition
last_transition_time: "2025-12-02T10:30:45.123456"  # When last transition occurred
```

#### Timer Information
```yaml
timers:                                  # Active timer details
  motion:
    remaining_seconds: 245               # Seconds until timer expires
    end_time: "2025-12-02T10:35:30"      # When timer will expire
```

#### Light Status
```yaml
lights_on: 2                             # Number of lights currently on
total_lights: 3                          # Total configured lights
```

#### Configuration Values
```yaml
brightness_active: 80                    # Configured active brightness
brightness_inactive: 10                  # Configured inactive brightness
```

#### Event History
```yaml
recent_events:                           # Detailed event log for debugging
  - timestamp: "2025-12-02T10:30:45"
    type: "motion_on"
    motion_activation: true
event_log:                               # Human-readable event log
  - "10:30:45 - Lights turned on by motion"
  - "10:32:00 - Lights adjusted manually"
```

### Using the Sensor in Automations

**Example 1: Notification when lights are stuck in manual**
```yaml
automation:
  - alias: "Notify: Kitchen lights in manual mode"
    trigger:
      - platform: state
        entity_id: sensor.kitchen_lighting_automation
        attribute: current_state
        to: "manual"
        for:
          minutes: 30
    action:
      - service: notify.mobile_app
        data:
          message: "Kitchen lights have been in manual mode for 30 minutes"
```

**Example 2: Dashboard card showing status**
```yaml
type: entities
entities:
  - entity: sensor.kitchen_lighting_automation
    name: Kitchen Automation
  - type: attribute
    entity: sensor.kitchen_lighting_automation
    attribute: current_state
    name: Current State
  - type: attribute
    entity: sensor.kitchen_lighting_automation
    attribute: motion_active
    name: Motion Active
  - type: attribute
    entity: sensor.kitchen_lighting_automation
    attribute: lights_on
    name: Lights On
```

**Example 3: Trigger when entering AUTO state**
```yaml
automation:
  - alias: "Kitchen lights entering countdown"
    trigger:
      - platform: state
        entity_id: sensor.kitchen_lighting_automation
        attribute: current_state
        to: "auto"
    action:
      - service: tts.speak
        data:
          message: "Kitchen lights will turn off in 5 minutes"
```

---

## Use Cases & Examples

### Example 1: Simple Bedroom

**Goal:** Turn on bedroom lights when motion detected, turn off after 5 minutes of no motion.

**Configuration:**
- Motion Sensors: `binary_sensor.bedroom_motion`
- Lights: `light.bedroom_ceiling`
- No Motion Wait: `300` (5 minutes)
- Brightness Active: `80`
- Brightness Inactive: `20`

**Behavior:**
- Motion detected → Lights turn on at 80%
- No motion for 5 minutes → Lights turn off
- Manual adjustment detected → Respects your setting until extended timer expires

### Example 2: Kitchen with Day/Night Modes

**Goal:** Bright lights during the day, dim lights at night, respect manual control.

**Configuration:**
- Motion Sensors: `binary_sensor.kitchen_motion`
- Lights: `light.kitchen_ceiling`, `light.kitchen_under_cabinet`
- Ambient Light Sensor: `binary_sensor.sun_below_horizon`
- No Motion Wait: `300`
- Brightness Active: `100` (day mode)
- Brightness Inactive: `10` (night mode)

**Behavior:**
- During day (sun above horizon): All lights at 100%
- At night (sun below horizon): All lights at 10%
- Manual adjustment → System backs off

### Example 3: Living Room with House Active Mode

**Goal:** Bright lights when house is active, dim lights when winding down for bed.

**Configuration:**
- Motion Sensors: `binary_sensor.living_room_motion`
- Lights: `light.living_room_main`, `light.living_room_lamp_1`, `light.living_room_lamp_2`, `light.living_room_accent`
- House Active: `input_boolean.house_active`
- No Motion Wait: `600` (10 minutes)
- Extended Timeout: `1800` (30 minutes)
- Brightness Active: `90`
- Brightness Inactive: `15`

**Automations to create:**
```yaml
# Turn house active mode ON in morning
automation:
  - alias: "House Active - Morning"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: input_boolean.turn_on
        target:
          entity_id: input_boolean.house_active

  - alias: "House Active - Evening Off"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.house_active
```

**Behavior:**
- 7 AM - 10 PM: All lights at 90% when motion detected
- 10 PM - 7 AM: All lights at 15% when motion detected
- Longer timers prevent lights turning off during movie watching
- Manual control still respected

### Example 4: Bathroom with Override

**Goal:** Auto lights normally, but disable automation when cleaning.

**Configuration:**
- Motion Sensors: `binary_sensor.bathroom_motion`
- Lights: `light.bathroom_ceiling`
- Override Switch: `input_boolean.bathroom_override`
- No Motion Wait: `180` (3 minutes)
- Brightness Active: `100`

**Behavior:**
- Normal operation: Lights on at 100% with motion, off after 3 minutes
- Override ON: Automation completely disabled, full manual control
- Override OFF: Automation resumes

---

## Troubleshooting Guide

### Real-Time Event Monitoring

The integration fires events to the Home Assistant event bus for real-time debugging and monitoring. This is **the best way** to understand what's happening inside the automation.

**Quick Start:**
1. Go to **Developer Tools** → **Events**
2. Listen to: `motion_lights_automation_state_changed`
3. Trigger your motion sensor
4. Watch state transitions appear in real-time

**Available Events:**
- `motion_lights_automation_state_changed` - State transitions
- `motion_lights_automation_motion_detected` - Motion events
- `motion_lights_automation_manual_intervention` - Manual control detected
- `motion_lights_automation_timer_expired` - Timer events
- `motion_lights_automation_override_activated/deactivated` - Override changes

Events are logged to the sensor's `recent_events` and `event_log` attributes for debugging.

### Lights Don't Turn On with Motion

**Check:**
1. Motion sensor is working: `Developer Tools` → `States` → verify sensor shows "on" when you move
2. Motion activation is enabled: Check advanced settings
3. Override switch is OFF: If configured, make sure it's not active
4. At least one light is configured
5. Check Home Assistant logs for errors: `Settings` → `System` → `Logs`

**Common Issue:** Motion sensor doesn't stay "on" long enough
- Some PIR sensors only trigger briefly
- Adjust your sensor's sensitivity or duration settings

### Lights Turn Off Too Quickly / Too Slowly

**Solution:**
- Adjust **No Motion Wait** in advanced settings
- Increase for slower shutoff, decrease for faster
- Remember: Timer starts when motion **stops**, not when lights turn on

### Manual Control Not Detected

**Check:**
1. You're adjusting brightness significantly (>10% change)
2. Or turning lights on/off manually via Home Assistant interface
3. Physical wall switches may not be detected (depends on integration)

**Workaround:** Use override switch if you need extended manual control

### Brightness Not Changing Between Active/Inactive

**Check:**
1. House active switch is configured and changing states
2. Or ambient light sensor is configured and changing states
3. Verify sensor states in `Developer Tools` → `States`

**Debug:** Check sensor attributes for `is_house_active` and `is_dark_inside`

### Lights Flicker or Behave Erratically

**Common Causes:**
1. Multiple automations controlling the same lights
2. Motion sensor too sensitive (triggering constantly)
3. Network issues with smart bulbs

**Solution:**
- Disable other automations for these lights
- Adjust motion sensor sensitivity
- Check light responsiveness: `Developer Tools` → `Services` → test turning on/off

### State Stuck in MANUAL or MANUAL_OFF

**This is by design:** Once you manually control lights, the system respects your choice.

**To reset:**
1. Wait for extended timeout to expire (default 20 minutes)
2. Or disable and re-enable motion activation
3. Or toggle override switch
4. Or reload the integration

### Integration Won't Load

**Check:**
1. All configured entities exist
2. Entity IDs are spelled correctly
3. Home Assistant logs for specific errors
4. Try removing and re-adding the integration

---

## Advanced Customization

### Custom Brightness Strategies

The integration uses a strategy pattern for brightness calculation. You can extend it by modifying `light_controller.py`:

```python
class LuxBasedBrightnessStrategy(BrightnessStrategy):
    """Adjust brightness based on ambient light sensor."""

    def __init__(self, hass: HomeAssistant, lux_sensor: str):
        self.hass = hass
        self.lux_sensor = lux_sensor

    def get_brightness(self, context: dict[str, Any]) -> int:
        state = self.hass.states.get(self.lux_sensor)
        if not state:
            return 80  # Default

        lux = float(state.state)
        if lux < 10:
            return 100  # Very dark
        elif lux < 50:
            return 80
        elif lux < 200:
            return 60
        else:
            return 40  # Bright enough
```

### Multiple Instances

You can create multiple instances of this integration for different areas:

1. Add integration → Configure for "Kitchen"
2. Add integration again → Configure for "Bedroom"
3. Add integration again → Configure for "Bathroom"

Each instance operates independently with its own state machine and timers.

---

## Integration with Other Systems

**Disable automation during specific times:**
```yaml
automation:
  - alias: "Disable Kitchen Motion at Night"
    trigger:
      - platform: time
        at: "23:00:00"
    action:
      - service: input_boolean.turn_on
        target:
          entity_id: input_boolean.kitchen_override

  - alias: "Enable Kitchen Motion in Morning"
    trigger:
      - platform: time
        at: "06:00:00"
    action:
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.kitchen_override
```

**Force lights off (bypass automation):**
```yaml
automation:
  - alias: "Force Kitchen Lights Off at Midnight"
    trigger:
      - platform: time
        at: "00:00:00"
    action:
      - service: light.turn_off
        target:
          entity_id:
            - light.kitchen_ceiling
            - light.kitchen_under_cabinet
```

### Presence Detection

Combine with presence detection for smarter control:

```yaml
# Create house_active switch based on presence
automation:
  - alias: "House Active Based on Presence"
    trigger:
      - platform: state
        entity_id: binary_sensor.anyone_home
    action:
      - service: input_boolean.turn_{{ 'on' if trigger.to_state.state == 'on' else 'off' }}
        target:
          entity_id: input_boolean.house_active
```

---

## Migration Guides

### From v4.x to v5.0 (Light Groups → Single Light Group)

Version 5.0 simplifies the architecture by combining light groups into a single instance model.

**What Changed:**
- One integration instance per light group instead of one instance managing multiple groups
- Single `Lights to Control` field replaces ceiling/background/feature groups
- Unique ID now includes lights to prevent duplicate instances
- ~150 lines of complexity removed from light selection logic

**Why This Change:**
The multi-group approach added unnecessary complexity. Most users wanted either all lights or a subset, not complex layered control. If you need different behaviors for different light types, create separate integration instances.

**Migration Steps:**

1. **Before upgrading:**
   - Note your current light assignments (ceiling/background/feature)
   - Take a screenshot of your configuration

2. **After upgrading to v5.0:**
   - Your existing instance will continue working with all configured lights combined
   - Reconfigure to adjust the light list if needed

3. **For per-group control:**
   - Delete your existing instance
   - Create separate instances for each light group you want to control differently
   - Example: "Kitchen Ceiling" (controls ceiling lights) + "Kitchen Ambient" (controls background lights)

**Migration Examples:**

**Simple Case (all lights behave the same):**
```yaml
# v4.x configuration
ceiling_lights: [light.ceiling1, light.ceiling2]
background_lights: [light.strip]
feature_lights: [light.accent]

# v5.0 configuration (single instance)
lights: [light.ceiling1, light.ceiling2, light.strip, light.accent]
```

**Complex Case (different timings for different lights):**
```yaml
# v4.x configuration (one instance)
ceiling_lights: [light.ceiling1, light.ceiling2]
background_lights: [light.strip]
no_motion_wait: 300

# v5.0 configuration (two instances)
Instance 1: "Kitchen Main"
  lights: [light.ceiling1, light.ceiling2]
  no_motion_wait: 300

Instance 2: "Kitchen Ambient"
  lights: [light.strip]
  no_motion_wait: 600  # Longer timeout for ambient
```

**Behavior Notes:**
- All lights in an instance turn on/off together
- All lights use the same brightness and timing settings
- Create multiple instances if you need different behaviors
- Each instance tracks its own state independently

---

### From Previous Version (Day/Night → Active/Inactive)

If you're upgrading from a version that used `brightness_day` and `brightness_night`:

**What Changed:**
- `brightness_day` → `brightness_active`
- `brightness_night` → `brightness_inactive`
- New: `house_active` switch support
- Brightness logic now has priority system

**Migration Steps:**

1. **Automatic via Reconfigure:**
   - Go to integration settings
   - Click "Reconfigure"
   - Your old settings will be migrated automatically
   - `brightness_day` value → `brightness_active`
   - `brightness_night` value → `brightness_inactive`

2. **Recommended Updates:**
   - Consider adding a `house_active` switch for more control
   - Review your brightness levels (defaults changed: active 80%, inactive 10%)

3. **Behavior Changes:**
   - If you had only `ambient_light_sensor` (or old `dark_inside`) configured: **No change in behavior**
   - Default brightness is now "active" (bright) instead of "day"
   - New priority system: house_active > ambient_light_sensor > default

**Example:**

**Old Configuration:**
```
brightness_day: 50
brightness_night: 5
dark_inside: binary_sensor.sun_below_horizon
```

**Migrated to:**
```
brightness_active: 50
brightness_inactive: 5
ambient_light_sensor: binary_sensor.sun_below_horizon
```

**Enhanced Configuration:**
```
brightness_active: 80
brightness_inactive: 10
ambient_light_sensor: binary_sensor.sun_below_horizon
house_active: input_boolean.house_active
```

---

## FAQ

### Q: Can I use multiple motion sensors?
**A:** Yes! Select multiple motion sensors during configuration. ANY of them triggering will activate the lights.

### Q: What happens if I manually adjust brightness?
**A:** The system detects this as manual intervention and transitions to MANUAL mode, respecting your setting. After the extended timeout, it returns to automatic mode.

### Q: Can I use this with groups?
**A:** Yes, but it's recommended to select individual lights for better control. If using groups, select the group entity.

### Q: Does this work with Zigbee/Z-Wave/WiFi lights?
**A:** Yes! It works with any light entity in Home Assistant, regardless of protocol.

### Q: Can I have different brightness for different lights?
**A:** Not currently. All lights use the same brightness level. This could be added as a future enhancement.

### Q: What if my motion sensor is too sensitive?
**A:** Adjust the sensor's sensitivity in its own configuration (depends on the sensor). You can also increase the "No Motion Wait" time to reduce cycling.

### Q: Can I use this with Adaptive Lighting?
**A:** Yes, but you may experience conflicts. Consider using the override switch when you want Adaptive Lighting to fully control the lights.

### Q: Does this work with HACS?
**A:** Not yet, but it can be installed manually. HACS support may be added in the future.

### Q: What's the performance impact?
**A:** Minimal. The integration is event-driven (no polling) and uses a single coordinator instance. Memory usage is ~1MB per configured instance.

---

## Technical Architecture

### Architecture

The integration uses a modular architecture with clear separation of concerns:

- **Coordinator** (`motion_coordinator.py`) - Orchestrates all components
- **State Machine** (`state_machine.py`) - Manages state transitions
- **Timer Manager** (`timer_manager.py`) - Handles motion and extended timers
- **Triggers** (`triggers.py`) - Manages event triggers (motion, override)
- **Light Controller** (`light_controller.py`) - Controls lights with strategies
- **Manual Detection** (`manual_detection.py`) - Detects manual interventions
- **Config Flow** (`config_flow.py`) - UI configuration
- **Sensor** (`sensor.py`) - Status sensor entity

### Design Patterns

- **State Machine Pattern** - Clean state management with callbacks
- **Strategy Pattern** - Pluggable brightness and light selection strategies
- **Observer Pattern** - Coordinator listeners for state updates
- **Manager Pattern** - Timer and trigger management

### Testing

The integration has comprehensive test coverage:
- State machine transitions
- Configuration flow
- Light controller behavior
- Coordinator logic
- Timer management
- Ambient light sensor detection
- YAML configuration import
- Edge cases and error handling

### Module Documentation

For developers and advanced users who want to extend the integration, see:
- **[Architecture Guide](ARCHITECTURE.md)** - System architecture and extension points
- **Module Docstrings** - Each Python file has comprehensive inline documentation
- **[Test Suite](../../tests/)** - Tests showing usage examples and edge cases

---

## Known Limitations

**Physical Controls:**
- Physical wall switches may not be detected as manual control (depends on how your lights report state changes)
- Some Zigbee/Z-Wave devices may not update state immediately

**Group Entities:**
- Using light groups instead of individual lights may cause less accurate state tracking
- Prefer selecting individual lights when possible

**Motion Sensors:**
- Very fast PIR sensors (<1 second on-time) may cause rapid state cycling
- Adjust sensor sensitivity or "No Motion Wait" to compensate

**Network/Performance:**
- WiFi bulbs may have slight delay in responding
- Very large number of lights (>10) may experience minor delays

**Context Tracking:**
- Some third-party integrations don't provide proper context IDs
- This may affect manual detection accuracy

---

## Future Enhancements

Planned features for future releases:

- 📊 **Diagnostics Support** - Download detailed troubleshooting data
- 💡 **Advanced Brightness Strategies** - Lux-based, seasonal, learning algorithms
- 🎨 **Per-light Brightness** - Different brightness for each light type


---

## Getting Help

**Before Asking for Help:**
1. Read the [Troubleshooting Guide](#troubleshooting-guide) above
2. Check your Home Assistant logs
3. Enable debug logging (see below)
4. Review the [FAQ](#faq) section

**Debug Logging:**
```yaml
# configuration.yaml
logger:
  default: info
  logs:
    custom_components.motion_lights_automation: debug
```

**Where to Ask:**
- **GitHub Issues:** Bug reports and feature requests
- **Home Assistant Community:** General questions and discussions
- **Discord:** Real-time help (Home Assistant server)

**When Reporting Issues, Include:**
- Home Assistant version
- Integration version
- Relevant configuration (sanitize entity IDs if needed)
- Debug logs showing the issue
- Steps to reproduce

---

**Last Updated:** December 2, 2025
