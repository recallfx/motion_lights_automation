"""Tests for integration lifecycle, diagnostic data, and configuration.

Covers:
- Coordinator setup and module initialization
- Coordinator cleanup (timers, listeners, periodic tasks)
- Diagnostic data accuracy across states
- Event log behavior and limits
- Coordinator data updates
- Startup grace period
- First light sync (KNX)
- Config defaults and custom values
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_EXTENDED_TIMEOUT,
    CONF_HOUSE_ACTIVE,
    CONF_LIGHTS,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
)
from custom_components.motion_lights_automation.state_machine import (
    STATE_AUTO,
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MOTION_AUTO,
    STATE_OVERRIDDEN,
)

from .conftest import CoordinatorHarness


# ============================================================================
# Coordinator Setup
# ============================================================================


class TestCoordinatorSetup:
    """Verify coordinator initializes modules, config, listeners, and initial state."""

    async def test_coordinator_initializes_all_modules(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Coordinator has state_machine, timer_manager, trigger_manager,
        light_controller, and manual_detector."""
        c = harness.coordinator
        assert c.state_machine is not None
        assert c.timer_manager is not None
        assert c.trigger_manager is not None
        assert c.light_controller is not None
        assert c.manual_detector is not None

    async def test_coordinator_loads_config_correctly(
        self, hass: HomeAssistant
    ) -> None:
        """Config values are loaded from ConfigEntry data."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_NO_MOTION_WAIT: 120,
                CONF_EXTENDED_TIMEOUT: 600,
                CONF_BRIGHTNESS_ACTIVE: 90,
                CONF_BRIGHTNESS_INACTIVE: 20,
                CONF_MOTION_ACTIVATION: False,
                CONF_OVERRIDE_SWITCH: "switch.override",
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 75,
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
            },
        )
        try:
            c = h.coordinator
            assert c._no_motion_wait == 120
            assert c.extended_timeout == 600
            assert c.brightness_active == 90
            assert c.brightness_inactive == 20
            assert c.motion_activation is False
            assert c.override_switch == "switch.override"
            assert c.ambient_light_sensor == "sensor.lux"
            assert c.ambient_light_threshold == 75
            assert c.house_active == "input_boolean.house_active"
        finally:
            await h.cleanup()

    async def test_coordinator_sets_up_listeners(self, hass: HomeAssistant) -> None:
        """State change listeners are set up for lights, motion, ambient,
        override, and house_active."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_OVERRIDE_SWITCH: "switch.override",
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
            },
        )
        try:
            c = h.coordinator
            # Unsubscribers for lights, ambient, and house_active
            assert len(c._unsubscribers) >= 3
            # Trigger manager has motion and override triggers
            assert c.trigger_manager.get_trigger("motion") is not None
            assert c.trigger_manager.get_trigger("override") is not None
        finally:
            await h.cleanup()

    async def test_coordinator_sets_initial_state_idle(
        self, hass: HomeAssistant
    ) -> None:
        """Lights off at startup -> IDLE."""
        h = await CoordinatorHarness.create(hass)
        try:
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_coordinator_sets_initial_state_motion_auto(
        self, hass: HomeAssistant
    ) -> None:
        """Lights on + motion on at startup -> MOTION_AUTO."""
        h = await CoordinatorHarness.create(
            hass,
            initial_motion="on",
            initial_lights={"light.ceiling": {"state": "on", "brightness": 200}},
            skip_grace_period=True,
        )
        try:
            h.assert_state(STATE_MOTION_AUTO)
        finally:
            await h.cleanup()

    async def test_coordinator_sets_initial_state_auto(
        self, hass: HomeAssistant
    ) -> None:
        """Lights on + no motion at startup -> AUTO with timer."""
        h = await CoordinatorHarness.create(
            hass,
            initial_motion="off",
            initial_lights={"light.ceiling": {"state": "on", "brightness": 200}},
            skip_grace_period=True,
        )
        try:
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")
        finally:
            await h.cleanup()

    async def test_coordinator_sets_initial_state_overridden(
        self, hass: HomeAssistant
    ) -> None:
        """Override on at startup -> OVERRIDDEN."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={CONF_OVERRIDE_SWITCH: "switch.override"},
            initial_override="on",
            skip_grace_period=True,
        )
        try:
            h.assert_state(STATE_OVERRIDDEN)
        finally:
            await h.cleanup()


# ============================================================================
# Coordinator Cleanup
# ============================================================================


class TestCoordinatorCleanup:
    """Verify cleanup cancels timers, listeners, periodic tasks, and watchdog."""

    async def test_cleanup_cancels_all_timers(self, hass: HomeAssistant) -> None:
        """All timers cancelled after cleanup."""
        h = await CoordinatorHarness.create(hass)
        await h.motion_on()
        await h.motion_off()
        h.assert_state(STATE_AUTO)
        h.assert_timer_active("motion")

        await h.cleanup()
        h.assert_no_active_timers()

    async def test_cleanup_removes_state_listeners(self, hass: HomeAssistant) -> None:
        """Listeners are unsubscribed during cleanup."""
        h = await CoordinatorHarness.create(hass)
        assert len(h.coordinator._unsubscribers) > 0

        await h.cleanup()
        assert len(h.coordinator._unsubscribers) == 0

    async def test_cleanup_cancels_periodic_tasks(self, hass: HomeAssistant) -> None:
        """cleanup_handle and reconciliation_handle cancelled."""
        h = await CoordinatorHarness.create(hass)
        assert h.coordinator._cleanup_handle is not None
        assert h.coordinator._reconciliation_handle is not None

        await h.cleanup()
        assert h.coordinator._cleanup_handle is None
        assert h.coordinator._reconciliation_handle is None

    async def test_cleanup_cancels_watchdog(self, hass: HomeAssistant) -> None:
        """Motion watchdog cancelled during cleanup."""
        h = await CoordinatorHarness.create(hass)
        await h.motion_on()
        h.assert_state(STATE_MOTION_AUTO)
        assert h.coordinator._motion_watchdog_handle is not None

        await h.cleanup()
        assert h.coordinator._motion_watchdog_handle is None

    async def test_double_cleanup_safe(self, hass: HomeAssistant) -> None:
        """Calling cleanup twice does not crash."""
        h = await CoordinatorHarness.create(hass)
        await h.cleanup()
        # Second cleanup should not raise
        await h.cleanup()


# ============================================================================
# Diagnostic Data
# ============================================================================


class TestDiagnosticData:
    """Verify diagnostic data accuracy across states."""

    async def test_diagnostic_data_in_idle(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """All fields present and correct for IDLE state."""
        harness.assert_state(STATE_IDLE)
        diag = harness.coordinator.get_diagnostic_data()

        assert diag["current_state"] == STATE_IDLE
        assert diag["motion_active"] is False
        assert "is_dark_inside" in diag
        assert "is_house_active" in diag
        assert "motion_activation_enabled" in diag
        assert "startup_grace_period_active" in diag
        assert "startup_grace_period_remaining" in diag
        assert "timers" in diag
        assert "lights_on" in diag
        assert "total_lights" in diag
        assert "recent_events" in diag
        assert "event_log" in diag
        assert "last_event_message" in diag
        assert "last_transition_reason" in diag
        assert "last_transition_time" in diag

    async def test_diagnostic_data_in_motion_auto(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """State is MOTION_AUTO, motion_active=True, timer info present."""
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        diag = harness.coordinator.get_diagnostic_data()
        assert diag["current_state"] == STATE_MOTION_AUTO
        assert diag["motion_active"] is True

    async def test_diagnostic_data_in_auto_with_timer(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Timer remaining_seconds > 0 in AUTO state."""
        await harness.motion_on()
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)

        diag = harness.coordinator.get_diagnostic_data()
        assert diag["current_state"] == STATE_AUTO
        # Should have a motion timer
        assert "motion" in diag["timers"]
        timer_data = diag["timers"]["motion"]
        assert timer_data["remaining_seconds"] is not None
        assert timer_data["remaining_seconds"] > 0

    async def test_diagnostic_data_in_manual(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """State is MANUAL, timer info for extended timer."""
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)

        diag = harness.coordinator.get_diagnostic_data()
        assert diag["current_state"] == STATE_MANUAL
        assert "extended" in diag["timers"]

    async def test_diagnostic_data_in_overridden(self, hass: HomeAssistant) -> None:
        """State is OVERRIDDEN."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={CONF_OVERRIDE_SWITCH: "switch.override"},
            initial_override="on",
        )
        try:
            h.assert_state(STATE_OVERRIDDEN)
            diag = h.coordinator.get_diagnostic_data()
            assert diag["current_state"] == STATE_OVERRIDDEN
        finally:
            await h.cleanup()

    async def test_diagnostic_data_shows_lights_count(
        self, hass: HomeAssistant
    ) -> None:
        """lights_on and total_lights are correct."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_LIGHTS: ["light.ceiling", "light.lamp"],
            },
            initial_lights={
                "light.ceiling": {"state": "on", "brightness": 200},
                "light.lamp": {"state": "off"},
            },
        )
        try:
            diag = h.coordinator.get_diagnostic_data()
            assert diag["total_lights"] == 2
            assert diag["lights_on"] == 1
        finally:
            await h.cleanup()

    async def test_diagnostic_data_shows_ambient(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """is_dark_inside reflects ambient sensor state."""
        # Initial ambient is 100 lx, threshold is 50, so not dark
        diag = ambient_harness.coordinator.get_diagnostic_data()
        assert diag["is_dark_inside"] is False

    async def test_diagnostic_data_shows_house_active(
        self, hass: HomeAssistant
    ) -> None:
        """is_house_active reflects house active entity."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={CONF_HOUSE_ACTIVE: "input_boolean.house_active"},
            initial_house_active="on",
        )
        try:
            diag = h.coordinator.get_diagnostic_data()
            assert diag["is_house_active"] is True
        finally:
            await h.cleanup()

    async def test_diagnostic_data_shows_motion_activation(
        self, hass: HomeAssistant
    ) -> None:
        """motion_activation_enabled reflects config."""
        h = await CoordinatorHarness.create(
            hass, config_data={CONF_MOTION_ACTIVATION: False}
        )
        try:
            diag = h.coordinator.get_diagnostic_data()
            assert diag["motion_activation_enabled"] is False
        finally:
            await h.cleanup()

    async def test_diagnostic_data_grace_period(self, hass: HomeAssistant) -> None:
        """startup_grace_period info during and after grace."""
        # During grace period (skip_grace_period=False)
        h = await CoordinatorHarness.create(hass, skip_grace_period=False)
        try:
            diag = h.coordinator.get_diagnostic_data()
            assert diag["startup_grace_period_active"] is True
            assert diag["startup_grace_period_remaining"] > 0

            # After grace period
            h.coordinator._startup_time = dt_util.now() - timedelta(seconds=200)
            diag = h.coordinator.get_diagnostic_data()
            assert diag["startup_grace_period_active"] is False
            assert diag["startup_grace_period_remaining"] == 0
        finally:
            await h.cleanup()


# ============================================================================
# Event Log
# ============================================================================


class TestEventLog:
    """Verify event log records events and respects limits."""

    async def test_event_log_records_motion_on(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Motion on logs an event."""
        harness.clear_event_log()
        await harness.motion_on()
        harness.assert_event_log_contains("motion")

    async def test_event_log_records_transitions(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """State transitions are logged."""
        harness.clear_event_log()
        await harness.motion_on()
        await harness.motion_off()
        # Should have transition events logged
        diag = harness.coordinator.get_diagnostic_data()
        assert len(diag["event_log"]) > 0

    async def test_event_log_records_manual_intervention(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Manual light change is logged."""
        harness.clear_event_log()
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)
        harness.assert_event_log_contains("manually")

    async def test_event_log_records_override(self, hass: HomeAssistant) -> None:
        """Override on/off events are logged."""
        h = await CoordinatorHarness.create(
            hass, config_data={CONF_OVERRIDE_SWITCH: "switch.override"}
        )
        try:
            h.clear_event_log()
            await h.override_on()
            h.assert_event_log_contains("overridden")

            h.clear_event_log()
            await h.override_off()
            h.assert_event_log_contains("override released")
        finally:
            await h.cleanup()

    async def test_event_log_max_entries(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Log does not exceed max entries (10)."""
        # Generate many events by cycling motion on/off
        for _ in range(15):
            await harness.motion_on()
            await harness.motion_off()
            await harness.expire_timer("motion")

        assert len(harness.coordinator._event_log) <= 10

    async def test_event_log_records_watchdog(self, hass: HomeAssistant) -> None:
        """Watchdog correction is logged."""
        h = await CoordinatorHarness.create(hass)
        try:
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            # Set motion sensor to off (simulating missed event)
            hass.states.async_set("binary_sensor.motion", "off")

            # Fire the watchdog
            await h.coordinator._async_motion_watchdog_fired()
            h.assert_event_log_contains("Watchdog")
        finally:
            await h.cleanup()

    async def test_event_log_records_reconciliation(self, hass: HomeAssistant) -> None:
        """Reconciliation correction is logged."""
        h = await CoordinatorHarness.create(hass)
        try:
            # Force state to AUTO with lights off (inconsistent)
            h.force_state(STATE_AUTO)
            hass.states.async_set("light.ceiling", "off")

            await h.coordinator._async_reconcile_state()
            h.assert_event_log_contains("Reconciliation")
        finally:
            await h.cleanup()


# ============================================================================
# Data Update
# ============================================================================


class TestDataUpdate:
    """Verify coordinator.data is updated after state changes."""

    async def test_data_updates_on_state_change(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """coordinator.data updated after each transition."""
        harness.assert_state(STATE_IDLE)
        data_before = dict(harness.coordinator.data)

        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)
        data_after = dict(harness.coordinator.data)
        assert data_before != data_after

    async def test_data_contains_current_state(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """data["current_state"] matches actual state."""
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)
        assert harness.coordinator.data["current_state"] == STATE_MOTION_AUTO

        await harness.motion_off()
        harness.assert_state(STATE_AUTO)
        assert harness.coordinator.data["current_state"] == STATE_AUTO

    async def test_data_contains_timer_info(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """data["timer_active"] and data["timer_type"] reflect timer state."""
        await harness.motion_on()
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)

        assert harness.coordinator.data["timer_active"] is True
        assert harness.coordinator.data["timer_type"] == "motion"

    async def test_data_contains_lights_on(self, hass: HomeAssistant) -> None:
        """data["lights_on"] reflects light count."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={CONF_LIGHTS: ["light.ceiling", "light.lamp"]},
            initial_lights={
                "light.ceiling": {"state": "on", "brightness": 200},
                "light.lamp": {"state": "off"},
            },
        )
        try:
            assert h.coordinator.data["lights_on"] == 1
        finally:
            await h.cleanup()

    async def test_data_contains_motion_activation(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """data["motion_activation"] matches config."""
        assert harness.coordinator.data["motion_activation"] is True


# ============================================================================
# Startup Grace Period
# ============================================================================


class TestStartupGracePeriod:
    """Verify grace period behavior for manual detection."""

    async def test_grace_period_prevents_manual_detection(
        self, hass: HomeAssistant
    ) -> None:
        """During grace period, light changes are ignored for manual detection."""
        h = await CoordinatorHarness.create(hass, skip_grace_period=False)
        try:
            h.assert_state(STATE_IDLE)
            # During grace period, a light change should not cause manual detection
            await h.manual_light_on("light.ceiling", brightness=200)
            # Should still be IDLE because manual detection is suppressed
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_grace_period_allows_motion(self, hass: HomeAssistant) -> None:
        """Motion detection works during grace period."""
        h = await CoordinatorHarness.create(hass, skip_grace_period=False)
        try:
            h.assert_state(STATE_IDLE)
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
        finally:
            await h.cleanup()

    async def test_grace_period_allows_override(self, hass: HomeAssistant) -> None:
        """Override works during grace period."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={CONF_OVERRIDE_SWITCH: "switch.override"},
            skip_grace_period=False,
        )
        try:
            h.assert_state(STATE_IDLE)
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)
        finally:
            await h.cleanup()

    async def test_after_grace_period_manual_detected(
        self, hass: HomeAssistant
    ) -> None:
        """After grace period, manual changes are detected normally."""
        h = await CoordinatorHarness.create(hass, skip_grace_period=True)
        try:
            h.assert_state(STATE_IDLE)
            await h.manual_light_on("light.ceiling", brightness=200)
            h.assert_state(STATE_MANUAL)
        finally:
            await h.cleanup()


# ============================================================================
# First Light Sync
# ============================================================================


class TestFirstLightSync:
    """Verify first KNX state sync for a light is not treated as manual."""

    async def test_first_light_state_not_treated_as_manual(
        self, hass: HomeAssistant
    ) -> None:
        """First state sync for a light is skipped for manual detection
        (tracked via _lights_initialized set)."""
        h = await CoordinatorHarness.create(hass, skip_grace_period=True)
        try:
            h.assert_state(STATE_IDLE)
            # Clear the initialized set to simulate a light whose first state
            # hasn't been seen yet
            h.coordinator._lights_initialized.discard("light.ceiling")
            # Also clear the light controller's internal tracked state so
            # the coordinator sees this as a first-time event
            h.coordinator.light_controller._light_states.pop("light.ceiling", None)

            # Simulate a raw state change (not via manual_light_on which patches
            # is_integration_context). This is an "external" change that
            # would normally be caught as manual, but first-seen should skip it.
            hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})
            await hass.async_block_till_done()

            # Should still be IDLE because first sync is ignored
            h.assert_state(STATE_IDLE)
            assert "light.ceiling" in h.coordinator._lights_initialized
        finally:
            await h.cleanup()

    async def test_subsequent_light_changes_are_checked(
        self, hass: HomeAssistant
    ) -> None:
        """Changes to lights whose state was already tracked by the light
        controller ARE checked for manual intervention.

        After setup, refresh_all_states() populates the light controller's
        internal state tracking, so subsequent state changes skip the
        first-seen code path and are evaluated normally.
        """
        h = await CoordinatorHarness.create(hass, skip_grace_period=True)
        try:
            h.assert_state(STATE_IDLE)

            # The light controller already has state for light.ceiling from
            # refresh_all_states() during setup. Any state change is checked
            # for manual intervention.
            await h.manual_light_on("light.ceiling", brightness=200)
            h.assert_state(STATE_MANUAL)
        finally:
            await h.cleanup()


# ============================================================================
# Config Defaults
# ============================================================================


class TestConfigDefaults:
    """Verify default config values and custom overrides."""

    async def test_minimal_config_uses_defaults(self, hass: HomeAssistant) -> None:
        """Only motion + lights specified, all other values use defaults."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.ceiling"],
            },
        )
        try:
            c = h.coordinator
            assert c.motion_activation is True
            assert c._no_motion_wait == 300
            assert c.extended_timeout == 1200
            assert c.brightness_active == 80
            assert c.brightness_inactive == 10
            assert c._motion_delay == 0
            assert c.override_switch is None
            assert c.ambient_light_sensor is None
            assert c.house_active is None
        finally:
            await h.cleanup()

    async def test_custom_timeouts_applied(self, hass: HomeAssistant) -> None:
        """Custom no_motion_wait and extended_timeout applied correctly."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_NO_MOTION_WAIT: 60,
                CONF_EXTENDED_TIMEOUT: 300,
            },
        )
        try:
            c = h.coordinator
            assert c._no_motion_wait == 60
            assert c.extended_timeout == 300
        finally:
            await h.cleanup()

    async def test_custom_brightness_applied(self, hass: HomeAssistant) -> None:
        """Custom brightness_active and brightness_inactive applied correctly."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_BRIGHTNESS_ACTIVE: 100,
                CONF_BRIGHTNESS_INACTIVE: 5,
            },
        )
        try:
            c = h.coordinator
            assert c.brightness_active == 100
            assert c.brightness_inactive == 5
        finally:
            await h.cleanup()
