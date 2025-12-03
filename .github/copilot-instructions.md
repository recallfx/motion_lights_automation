# Motion Lights Automation - AI Agent Instructions

## Skill files

Detailed development guides are available in `.github/skills/`:

- **`ha-component.md`** - Home Assistant component development (state machine, timers, triggers, config flow)
- **`simulation.md`** - Simulation server and industrial dashboard UI (WebSocket API, Lit components, styling)
- **`testing.md`** - Testing patterns, fixtures, mocks, and common pitfalls

## Architecture overview

This Home Assistant integration uses a modular coordinator pattern with five independent components. The coordinator (`motion_coordinator.py`) wires components together but delegates all logic to specialized modules:

- `state_machine.py` - manages transitions between 7 states (IDLE, MOTION_AUTO, AUTO, MANUAL, MOTION_MANUAL, MANUAL_OFF, OVERRIDDEN)
- `timer_manager.py` - handles motion timers (short) and extended timers (long) with lifecycle management
- `light_controller.py` - controls lights using pluggable brightness and selection strategies
- `triggers.py` - event handlers for motion sensors and override switches, extensible via TriggerHandler base class
- `manual_detection.py` - detects when users manually adjust lights using configurable strategies

The coordinator initializes modules in `__init__`, wires callbacks in `async_setup_listeners()`, and delegates state transitions to the state machine. Components communicate through callbacks, not direct method calls.

## Critical patterns

**Motion activation disabled behavior**: When `motion_activation=False`, the MotionTrigger still fires callbacks (lines 141-169 in `triggers.py`). The coordinator handles this in `_handle_motion_on()` by resetting the extended timer without transitioning states. This prevents lights from turning off after 20 minutes when a room is actively used but motion shouldn't auto-enable lights.

**State machine transitions**: Use `StateTransitionEvent` enum values, not raw strings. The state machine validates transitions and prevents invalid ones. Always check `state_machine.py` lines 40-80 for the transition table before adding new transitions.

**Timer management**: The TimerManager uses `TimerType` enum (MOTION, EXTENDED, CUSTOM). Access timers by name string, not type. Use `has_active_timer(name)` not `is_timer_active()`. Timer start times are private (`_start_time`) - use `end_time` property or `remaining_seconds` instead.

**Light context tracking**: The LightController tracks which context IDs originated from the integration using `is_integration_context()`. This distinguishes automation-triggered changes from manual interventions. Context cleanup happens every hour via `_schedule_periodic_cleanup()`.

## Testing commands

Run tests with `uv run pytest tests/` (not `pytest` directly - uv manages the environment). Tests use pytest-homeassistant-custom-component which provides fixtures like `hass` and `MockConfigEntry`.

For new test files, use `ConfigEntry` from `homeassistant.config_entries`, not a custom mock. Required parameters: version, minor_version, domain, title, data, options, entry_id, source, unique_id, discovery_keys.

Always call `coordinator.async_cleanup_listeners()` in test teardown to prevent lingering timer errors. The test framework checks for uncanceled timers.

## Extension patterns

Add new triggers by subclassing `TriggerHandler` (see `triggers.py` lines 19-100). Implement `async_setup()`, `is_active()`, and `get_info()`. Register with `trigger_manager.add_trigger(name, instance)`.

Add brightness logic by subclassing `BrightnessStrategy` and implementing `get_brightness(context)`. Context dict includes `is_house_active`, `is_dark_inside`, `motion_active`. Register with `light_controller.set_brightness_strategy()`.

Add manual detection logic by subclassing `ManualInterventionStrategy`. The base class provides `is_integration_context()`. Return tuple of (is_manual: bool, reason: str) from `is_manual_intervention()`.

## Config flow specifics

The config flow uses two steps: basic setup collects entities, advanced setup collects timeouts and brightness. Use `vol.All(cv.ensure_list, [cv.entity_id])` for multi-entity fields, not `vol.Any()`.

Entity validation happens in `_validate_input()` which checks for at least one light type. Don't validate entity existence - Home Assistant handles that.

Reconfiguration reuses the same flow with pre-filled data. Use `self.config_entry.data.get(key, default)` when building schemas.

## Common pitfalls

Don't check `trigger.enabled` in `_async_motion_changed()` - always fire callbacks. The coordinator decides whether to act based on `motion_activation`.

Don't use `timer.start_time` - it's private. Use `timer.end_time` or `timer.remaining_seconds` instead.

Don't import from `homeassistant.components.motion_lights_automation` - this is a custom component, use `custom_components.motion_lights_automation`.

The state sensor updates via `coordinator.async_update_listeners()`, not by calling `async_write_ha_state()` directly. The coordinator maintains `self.data` dict which sensors read.

## File organization

Tests mirror the source structure: `tests/motion_lights_automation/test_*.py` corresponds to `custom_components/motion_lights_automation/*.py`. Use `conftest.py` for shared fixtures.

The `motion_lights_automation_rig` is a test helper integration that provides mock entities. Don't modify it unless adding new entity types for testing.

Constants go in `const.py` using uppercase names. State strings use lowercase with hyphens (STATE_MOTION_AUTO = "motion-auto").

## Readme writing style

Write like a human, not an AI. Avoid flowery language, summary phrases, generic lists, vague statements, and common AI patterns. Use clear, accurate, and natural language with real-world detail and nuance.
