# Refactoring Guide: Single Instance Per Light Group

## ✅ Completed Changes

### 1. const.py
- ✅ Removed `CONF_BACKGROUND_LIGHT`, `CONF_FEATURE_LIGHT`, `CONF_CEILING_LIGHT`
- ✅ Added `CONF_LIGHTS`

### 2. config_flow.py  
- ✅ Simplified to one multi-entity selector for lights
- ✅ Updated validation to check single `CONF_LIGHTS` field
- ✅ Updated unique ID generation to include lights (prevents same lights in multiple instances)

### 3. light_controller.py
- ✅ Removed `LightSelectionStrategy` and `TimeOfDayLightSelectionStrategy`
- ✅ Changed `light_groups: dict` to `lights: list[str]`
- ✅ Updated `turn_on_auto_lights()` to turn on all lights (no selection logic)
- ✅ Updated `turn_off_lights()` to use flat list
- ✅ Updated `get_info()` to return flat light list

## 🚧 Remaining Changes

### 4. motion_coordinator.py

**Current code (lines ~50-70):**
```python
# Build light groups from config
light_groups = {}
if background := config_data.get(CONF_BACKGROUND_LIGHT):
    light_groups["background"] = _as_list(background)
if feature := config_data.get(CONF_FEATURE_LIGHT):
    light_groups["feature"] = _as_list(feature)
if ceiling := config_data.get(CONF_CEILING_LIGHT):
    light_groups["ceiling"] = _as_list(ceiling)

self.light_controller = LightController(hass, light_groups, ...)
```

**Change to:**
```python
# Get lights from config
lights = _as_list(config_data.get(CONF_LIGHTS, []))

self.light_controller = LightController(hass, lights, ...)
```

**Property accessors to remove/update:**
- Remove `background_light_entity`, `feature_light_entity`, `ceiling_light_entity` properties
- Add single `lights` property that returns `self.light_controller.lights`

### 5. sensor.py

**Update `extra_state_attributes` (lines ~80-120):**

**Remove these attributes:**
```python
"background_light": self.coordinator.background_light_entity,
"feature_light": self.coordinator.feature_light_entity,
"ceiling_light": self.coordinator.ceiling_light_entity,
```

**Add this attribute:**
```python
"lights": self.coordinator.lights,  # Returns list of all light entity IDs
```

### 6. strings.json

**Change from:**
```json
"data": {
  "background_light": "Background lights",
  "feature_light": "Feature lights", 
  "ceiling_light": "Ceiling lights"
}
```

**To:**
```json
"data": {
  "lights": "Lights to control"
}
```

**Update descriptions:**
```json
"data_description": {
  "lights": "Select the lights this automation should control"
}
```

### 7. translations/en.json

Same changes as strings.json - update all occurrences of light group fields to single `lights` field.

### 8. Test Files

#### conftest.py (test fixtures)
**Change from:**
```python
CONF_BACKGROUND_LIGHT: ["light.background"],
CONF_FEATURE_LIGHT: ["light.feature"],
CONF_CEILING_LIGHT: ["light.ceiling"],
```

**To:**
```python
CONF_LIGHTS: ["light.background", "light.feature", "light.ceiling"],
```

#### test_light_controller.py
**Remove:**
- All tests for `LightSelectionStrategy`
- All tests for `TimeOfDayLightSelectionStrategy`
- Tests that check group-based logic

**Update fixture:**
```python
# Change from:
light_groups = {"ceiling": ["light.c1"], "background": ["light.bg1"]}
controller = LightController(hass, light_groups)

# To:
lights = ["light.c1", "light.bg1"]
controller = LightController(hass, lights)
```

#### test_config_flow.py
**Update test data:**
```python
# Change from:
user_input={
    CONF_NAME: "Test",
    CONF_BACKGROUND_LIGHT: ["light.bg1"],
    CONF_FEATURE_LIGHT: ["light.feature"],
    CONF_CEILING_LIGHT: ["light.ceiling"],
}

# To:
user_input={
    CONF_NAME: "Test",
    CONF_LIGHTS: ["light.bg1", "light.feature", "light.ceiling"],
}
```

#### test_motion_activation_disabled.py
Update all test config dictionaries to use `CONF_LIGHTS` instead of group fields.

### 9. Update manifest version
Increment version to 5.0.0 (breaking change):
```json
{
  "version": "5.0.0"
}
```

### 10. Documentation Updates

#### README.md
**Add migration section:**
```markdown
## Migration from v4.x to v5.x

**Breaking Change:** v5.0 uses one integration instance per light group.

### Before (v4.x):
One instance with three light groups:
- Background lights: light.bg1, light.bg2
- Feature lights: light.feature
- Ceiling lights: light.ceiling

### After (v5.x):
Create three separate instances:

**Instance 1: "Kitchen Background"**
- Lights: light.bg1, light.bg2
- Brightness active: 50%

**Instance 2: "Kitchen Feature"**
- Lights: light.feature
- Brightness active: 75%

**Instance 3: "Kitchen Ceiling"**  
- Lights: light.ceiling
- Brightness active: 100%

Each instance can have:
- Different brightness levels
- Different motion sensors
- Different timeouts
- Independent state machines
```

#### ARCHITECTURE.md
Update examples to reflect single instance pattern.

## Testing Checklist

```bash
# 1. Update all imports
grep -r "CONF_BACKGROUND_LIGHT\|CONF_FEATURE_LIGHT\|CONF_CEILING_LIGHT" custom_components/ tests/

# 2. Run tests
uv run pytest tests/

# 3. Fix failures one by one
uv run pytest tests/motion_lights_automation/test_config_flow.py -v
uv run pytest tests/motion_lights_automation/test_light_controller.py -v
uv run pytest tests/motion_lights_automation/test_coordinator_simple.py -v

# 4. Run full suite
uv run pytest tests/ --cov=custom_components/motion_lights_automation
```

## Estimated Time for Remaining Work

- Coordinator updates: 30 min
- Sensor updates: 15 min
- Strings/translations: 10 min
- Test updates: 1-2 hours (most time-consuming)
- Documentation: 30 min

**Total remaining: ~3 hours**

## Benefits Summary

- **~150 lines of code removed** (LightSelectionStrategy + group logic)
- **Simpler config flow** (3 fields → 1 field)
- **Clearer user model** (one instance = one group of lights)
- **More flexible** (each instance fully independent)
- **Easier to test** (less complex fixtures)
