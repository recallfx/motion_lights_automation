# Motion Lights Automation Test Rig

**Complete testing environment for the Motion Lights Automation integration**

This test rig provides mock entities that simulate a real motion-activated lighting environment, making it easy to test and develop the `motion_lights_automation` integration without needing physical devices.

---

## 🎯 What This Does

Creates a complete set of virtual entities for testing motion-activated lighting:
- **Motion sensor** with easy control
- **Three types of lights** (ceiling, background, feature)
- **Control switches** (override, dark inside, house active)
- **Automated synchronization** between motion sensor and toggle switch

Perfect for:
- ✅ Testing `motion_lights_automation` behavior
- ✅ Developing new features
- ✅ Demonstrating functionality
- ✅ Creating tutorials/documentation

---

## 📦 Installation

### Step 1: Copy Files
```bash
# Already in custom_components/motion_lights_automation_rig/
# No additional installation needed if you have this folder
```

### Step 2: Add Integration
1. **Restart Home Assistant**
2. Go to **Settings** → **Devices & Services**
3. Click **+ Add Integration**
4. Search for "Motion Lights Automation Rig"
5. Enter a room name (e.g., "Living Room", "Kitchen", "Bedroom")
6. Click **Submit**

### Step 3: Configure Motion Lights Automation
1. Add the **Motion Lights Automation** integration
2. Configure it using the test rig entities
3. Start testing!

---

## 🏷️ Entities Created

When you create a test rig instance for "Living Room", you get:

### Motion Detection
| Entity ID | Type | Description |
|-----------|------|-------------|
| `binary_sensor.living_room_motion` | Binary Sensor | Motion sensor (ON/OFF) |
| `switch.living_room_motion_toggle` | Switch | Control motion sensor state |

### Lights
| Entity ID | Type | Description |
|-----------|------|-------------|
| `light.living_room_ceiling_light` | Light | Main ceiling/overhead light |
| `light.living_room_background_light` | Light | Ambient/background lighting |
| `light.living_room_feature_light` | Light | Accent/feature lights |

### Control Switches
| Entity ID | Type | Description |
|-----------|------|-------------|
| `switch.living_room_override` | Switch | Override automation (ON = automation disabled) |
| `switch.living_room_dark_inside` | Switch | Simulate dark inside (ON = dark) |
| `input_boolean.living_room_house_active` | Input Boolean | House active state (ON = active/bright) |

---

## 🎮 How to Use

### Quick Test Flow

1. **Toggle Motion ON**
   ```yaml
   service: switch.turn_on
   target:
     entity_id: switch.living_room_motion_toggle
   ```
   - Motion sensor activates
   - Lights turn on per automation config
   - Watch state transitions

2. **Toggle Motion OFF**
   ```yaml
   service: switch.turn_off
   target:
     entity_id: switch.living_room_motion_toggle
   ```
   - Motion sensor clears
   - Timers start counting down
   - Lights turn off after timeout

3. **Test Brightness Modes**
   - Toggle `switch.living_room_dark_inside` ON → inactive/night mode (dim)
   - Toggle `input_boolean.living_room_house_active` OFF → inactive mode (dim)
   - Toggle both OFF → active mode (bright)

4. **Test Override**
   - Toggle `switch.living_room_override` ON → automation disabled
   - Toggle OFF → automation resumes

### Dashboard Card Example

Add this to your dashboard for easy testing:

```yaml
type: entities
title: Living Room Test Rig
entities:
  # Motion Control
  - entity: switch.living_room_motion_toggle
    name: Motion Toggle
    icon: mdi:motion-sensor
  - entity: binary_sensor.living_room_motion
    name: Motion Sensor
  
  # Lights
  - type: section
    label: Lights
  - entity: light.living_room_ceiling_light
  - entity: light.living_room_background_light
  - entity: light.living_room_feature_light
  
  # Controls
  - type: section
    label: Controls
  - entity: switch.living_room_override
    name: Override Automation
  - entity: switch.living_room_dark_inside
    name: Dark Inside
  - entity: input_boolean.living_room_house_active
    name: House Active
  
  # Automation Status
  - type: section
    label: Automation
  - entity: sensor.living_room_motion_lights_automation_status
    name: Automation Status
```

---

## 🧪 Testing Scenarios

### Scenario 1: Basic Motion Detection
```yaml
# Turn on motion
service: switch.turn_on
target:
  entity_id: switch.living_room_motion_toggle

# Wait 2 seconds, verify lights are on
# Turn off motion  
service: switch.turn_off
target:
  entity_id: switch.living_room_motion_toggle

# Wait for no_motion_wait timeout (default 300s)
# Verify lights turn off
```

### Scenario 2: Active vs Inactive Brightness
```yaml
# Set to active mode (bright)
service: input_boolean.turn_on
target:
  entity_id: input_boolean.living_room_house_active
service: switch.turn_off
target:
  entity_id: switch.living_room_dark_inside

# Trigger motion - lights should be bright (80%)
service: switch.turn_on
target:
  entity_id: switch.living_room_motion_toggle

# Change to inactive mode (dim)
service: input_boolean.turn_off
target:
  entity_id: input_boolean.living_room_house_active

# Lights should adjust to dim (10%)
```

### Scenario 3: Manual Intervention
```yaml
# Trigger motion
service: switch.turn_on
target:
  entity_id: switch.living_room_motion_toggle

# Manually adjust brightness
service: light.turn_on
target:
  entity_id: light.living_room_ceiling_light
data:
  brightness_pct: 50

# Check automation status - should show "manual" state
```

### Scenario 4: Override Testing
```yaml
# Enable override (disable automation)
service: switch.turn_on
target:
  entity_id: switch.living_room_override

# Trigger motion - lights should NOT turn on
service: switch.turn_on
target:
  entity_id: switch.living_room_motion_toggle

# Disable override
service: switch.turn_off
target:
  entity_id: switch.living_room_override

# Trigger motion - lights should turn on now
```

---

## 🔄 Motion Toggle Synchronization

The **Motion Toggle Switch** and **Motion Sensor** stay perfectly synchronized:

**When you toggle the switch:**
- `switch.motion_toggle` ON → `binary_sensor.motion` turns ON
- `switch.motion_toggle` OFF → `binary_sensor.motion` turns OFF

**Automatic sync:**
- Both entities always reflect the same state
- No manual coordination needed
- Works through UI, automations, or services

---

## 🎨 Integration Configuration Example

Use these test rig entities in your Motion Lights Automation config:

### Step 1: Add Motion Lights Automation
1. Settings → Devices & Services → Add Integration
2. Search "Motion Lights Automation"

### Step 2: Basic Configuration
- **Name:** Living Room Motion Lights
- **Motion Sensors:** `binary_sensor.living_room_motion`
- **Ceiling Lights:** `light.living_room_ceiling_light`
- **Background Lights:** `light.living_room_background_light`
- **Feature Lights:** `light.living_room_feature_light`
- **Override Switch:** `switch.living_room_override`
- **House Active Switch:** `input_boolean.living_room_house_active`
- **Dark Inside Sensor:** `switch.living_room_dark_inside`

### Step 3: Advanced Settings
- **Motion Activation:** Enabled
- **No Motion Wait:** 300s (5 minutes)
- **Extended Timeout:** 1200s (20 minutes)
- **Brightness Active:** 80%
- **Brightness Inactive:** 10%

---

## 🔍 Monitoring & Debugging

### Check Automation Status
The Motion Lights Automation integration creates a status sensor:
- **Entity:** `sensor.living_room_motion_lights_automation_status`
- **States:** `idle`, `motion_auto`, `auto`, `motion_manual`, `manual`, `manual_off`, `overridden`

### View Attributes
```yaml
current_state: auto
timer_active: true
time_until_action: 280
brightness_active: 80
brightness_inactive: 10
current_brightness_mode: active
motion_entity: binary_sensor.living_room_motion
```

### Enable Debug Logging
Add to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.motion_lights_automation: debug
    custom_components.motion_lights_automation_rig: debug
```

---

## 📝 Tips & Best Practices

### Testing Tips
1. **Use the dashboard card** for quick manual testing
2. **Create automations** to test different scenarios automatically
3. **Monitor the status sensor** to understand state transitions
4. **Check logs** when behavior is unexpected
5. **Test edge cases** like rapid motion on/off toggles

### Common Test Patterns
```yaml
# Rapid motion pattern (simulate someone walking through)
- service: switch.turn_on
  target:
    entity_id: switch.living_room_motion_toggle
- delay: 2
- service: switch.turn_off
  target:
    entity_id: switch.living_room_motion_toggle
- delay: 5
- service: switch.turn_on
  target:
    entity_id: switch.living_room_motion_toggle

# Simulate day/night cycle
- service: switch.turn_off
  target:
    entity_id: switch.living_room_dark_inside
- delay: 120  # Test day mode for 2 minutes
- service: switch.turn_on
  target:
    entity_id: switch.living_room_dark_inside
```

### Development Workflow
1. Make code changes to `motion_lights_automation`
2. Restart Home Assistant
3. Use test rig to verify behavior
4. Check logs for errors
5. Iterate

---

## 🐛 Troubleshooting

### Motion not triggering lights
**Check:**
- Override switch is OFF
- Motion Lights Automation is configured
- Motion sensor entity is correct
- Lights are reachable

### Lights not turning off
**Check:**
- No motion wait timeout setting
- Check if stuck in MANUAL state (manual intervention detected)
- Verify timer status in status sensor attributes

### Brightness not changing
**Check:**
- House active and dark inside switch states
- Brightness active/inactive settings
- Current brightness mode in status sensor

### Test rig entities not appearing
**Check:**
- Integration added successfully
- Restart Home Assistant after installation
- Check `configuration.yaml` for conflicts

---

## 🔧 Technical Details

### Entity Domains
- **Binary Sensor:** Motion detection
- **Light:** Dimmable lights with brightness control
- **Switch:** Toggle switches for override and dark inside
- **Input Boolean:** House active state

### State Synchronization
Motion toggle and motion sensor use Home Assistant's state change events to stay synchronized. When either changes, the other updates automatically.

### Light Capabilities
All test rig lights support:
- ✅ On/Off control
- ✅ Brightness (0-255 / 0-100%)
- ✅ Color temperature
- ✅ RGB color
- ✅ State restoration

---

## 📚 Related Documentation

- **Motion Lights Automation:** Main integration documentation
- **Home Assistant Docs:** https://www.home-assistant.io/docs/
- **State Machine:** See Motion Lights Automation README for state diagram

---

## 🎓 Example: Complete Test Session

```yaml
# 1. Setup - Create test rig instance "Test Room"
# 2. Configure Motion Lights Automation with test entities
# 3. Run this automation:

automation:
  - alias: "Motion Lights Complete Test"
    trigger:
      - platform: time
        at: "10:00:00"
    action:
      # Test 1: Basic motion
      - service: switch.turn_on
        target:
          entity_id: switch.test_room_motion_toggle
      - delay: 5
      - service: switch.turn_off
        target:
          entity_id: switch.test_room_motion_toggle
      
      # Test 2: Brightness modes
      - delay: 10
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.test_room_house_active
      - service: switch.turn_on
        target:
          entity_id: switch.test_room_motion_toggle
      - delay: 5
      - service: switch.turn_off
        target:
          entity_id: switch.test_room_motion_toggle
      
      # Test 3: Override
      - delay: 10
      - service: switch.turn_on
        target:
          entity_id: switch.test_room_override
      - service: switch.turn_on
        target:
          entity_id: switch.test_room_motion_toggle
      - delay: 5
      - service: switch.turn_off
        target:
          entity_id: switch.test_room_override
```

---

## 📄 License

Part of the Motion Lights Automation project.

---

## 👤 Credits

**Author:** recallfx  
**Purpose:** Testing and development for Motion Lights Automation  
**Integration Type:** Helper

---

**Last Updated:** October 23, 2025

---

## 🚀 Quick Start Checklist

- [ ] Test rig installed in `custom_components/motion_lights_automation_rig/`
- [ ] Home Assistant restarted
- [ ] Test rig instance created (Settings → Devices & Services)
- [ ] Motion Lights Automation installed
- [ ] Motion Lights Automation configured with test rig entities
- [ ] Dashboard card added for easy testing
- [ ] Test automation created (optional)
- [ ] Debug logging enabled (optional)
- [ ] Ready to test! 🎉
