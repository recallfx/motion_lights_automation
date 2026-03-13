"""Pipeline tests for edge cases, startup, grace period, and diagnostics.

Covers startup initialization, grace-period behavior, entity unavailability,
rapid state changes, event logging, diagnostic data, and cleanup.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.motion_lights_automation.const import (
    CONF_OVERRIDE_SWITCH,
)
from custom_components.motion_lights_automation.state_machine import (
    STATE_AUTO,
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_MOTION_AUTO,
    STATE_MOTION_MANUAL,
    STATE_OVERRIDDEN,
)
from tests.motion_lights_automation.pipeline.conftest import CoordinatorHarness


# ===================================================================
# TestStartupBehavior
# ===================================================================


class TestStartupBehavior:
    """Verify initial state determination on startup."""

    async def test_startup_with_lights_off_initializes_idle(
        self, hass: HomeAssistant
    ) -> None:
        """Lights off at startup -> IDLE."""
        h = await CoordinatorHarness.create(hass, skip_grace_period=False)
        try:
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_startup_with_lights_on_no_motion(self, hass: HomeAssistant) -> None:
        """Lights on, no motion at startup -> AUTO (with motion timer)."""
        h = await CoordinatorHarness.create(
            hass,
            initial_lights={
                "light.ceiling": {"state": "on", "brightness": 200},
            },
            skip_grace_period=False,
        )
        try:
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")
        finally:
            await h.cleanup()

    async def test_startup_with_lights_on_and_motion(self, hass: HomeAssistant) -> None:
        """Lights on + motion active at startup -> MOTION_AUTO."""
        h = await CoordinatorHarness.create(
            hass,
            initial_motion="on",
            initial_lights={
                "light.ceiling": {"state": "on", "brightness": 200},
            },
            skip_grace_period=False,
        )
        try:
            h.assert_state(STATE_MOTION_AUTO)
        finally:
            await h.cleanup()

    async def test_startup_with_override_on(self, hass: HomeAssistant) -> None:
        """Override switch on at startup -> OVERRIDDEN."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_OVERRIDE_SWITCH: "switch.override",
            },
            initial_override="on",
            skip_grace_period=False,
        )
        try:
            h.assert_state(STATE_OVERRIDDEN)
        finally:
            await h.cleanup()


# ===================================================================
# TestGracePeriod
# ===================================================================


class TestGracePeriod:
    """Verify startup grace-period filtering."""

    async def test_light_changes_during_grace_period_ignored(
        self, hass: HomeAssistant
    ) -> None:
        """Manual light changes during grace period do NOT change state."""
        h = await CoordinatorHarness.create(hass, skip_grace_period=False)
        try:
            h.assert_state(STATE_IDLE)

            # Manual light on during grace period - should be ignored
            await h.manual_light_on("light.ceiling", brightness=200)
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_light_changes_after_grace_period_detected(
        self, hass: HomeAssistant
    ) -> None:
        """Manual light changes after grace period DO change state (default harness skips)."""
        h = await CoordinatorHarness.create(hass, skip_grace_period=True)
        try:
            h.assert_state(STATE_IDLE)

            await h.manual_light_on("light.ceiling", brightness=200)
            h.assert_state(STATE_MANUAL)
        finally:
            await h.cleanup()


# ===================================================================
# TestEntityUnavailability
# ===================================================================


class TestEntityUnavailability:
    """Verify behavior when entities become unavailable."""

    async def test_motion_sensor_unavailable(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Motion sensor going unavailable then back to on recovers correctly."""
        # Set to unavailable
        hass.states.async_set("binary_sensor.motion", "unavailable")
        await hass.async_block_till_done()

        # Set back to "on" - should trigger motion detection
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

    async def test_light_entity_unavailable(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Light entity that is unavailable reports as not on."""
        hass.states.async_set("light.ceiling", "unavailable")
        await hass.async_block_till_done()
        harness.refresh_lights()

        assert harness.coordinator.light_controller.any_lights_on() is False


# ===================================================================
# TestRapidStateChanges
# ===================================================================


class TestRapidStateChanges:
    """Verify correct behavior under rapid event sequences."""

    async def test_rapid_motion_on_off_on(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Rapid motion on -> off -> on settles in MOTION_AUTO."""
        await harness.motion_on()
        await harness.motion_off()
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

    async def test_rapid_manual_changes(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Rapid manual off/on/off in MOTION_AUTO ends in a consistent state."""
        # Get into MOTION_AUTO with light on
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        await harness.light_on("light.ceiling", brightness=200)
        harness.refresh_lights()

        # Rapid manual changes: off, on, off
        await harness.manual_light_off("light.ceiling")
        await harness.manual_light_on("light.ceiling", brightness=200)
        await harness.manual_light_off("light.ceiling")

        # State should be consistent - either MANUAL_OFF (all lights off with manual off)
        # or some manual state. The key is no crash and a valid state.
        current = harness.state
        assert current in (
            STATE_MANUAL_OFF,
            STATE_MOTION_MANUAL,
            STATE_MANUAL,
            STATE_IDLE,
        ), f"Unexpected state after rapid changes: {current}"


# ===================================================================
# TestEventLogging
# ===================================================================


class TestEventLogging:
    """Verify event logging on state transitions."""

    async def test_transition_logging(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """State transition creates an entry in the _events list."""
        harness.clear_event_log()

        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        # The _events list should contain a state_transition entry
        transitions = [
            e
            for e in harness.coordinator._events
            if e.get("type") == "state_transition"
        ]
        assert len(transitions) > 0, (
            f"Expected at least one state_transition event, got: {harness.coordinator._events}"
        )

    async def test_human_event_log_on_enter_idle_from_auto(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """AUTO -> expire timer -> IDLE logs 'timeout' in human event log."""
        await harness.motion_on()
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)

        harness.clear_event_log()
        await harness.expire_timer("motion")
        harness.assert_state(STATE_IDLE)

        harness.assert_event_log_contains("timeout")

    async def test_human_event_log_on_manual_on_from_idle(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """IDLE -> manual on -> MANUAL logs 'manually' in human event log."""
        harness.force_state(STATE_IDLE)
        harness.clear_event_log()

        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)

        harness.assert_event_log_contains("manually")

    async def test_event_log_max_size(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Event log does not grow beyond its configured maximum."""
        max_log = harness.coordinator._max_log_entries

        # Generate many events by cycling through states
        for _ in range(max_log + 20):
            harness.coordinator._log_human_event("test event")

        assert len(harness.coordinator._event_log) <= max_log, (
            f"Event log grew to {len(harness.coordinator._event_log)}, "
            f"expected max {max_log}"
        )


# ===================================================================
# TestDiagnosticData
# ===================================================================


class TestDiagnosticData:
    """Verify diagnostic data structure and content."""

    async def test_get_diagnostic_data_has_all_keys(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Diagnostic data includes essential keys."""
        diag = harness.coordinator.get_diagnostic_data()

        expected_keys = {
            "current_state",
            "timers",
            "lights_on",
            "total_lights",
            "motion_active",
            "event_log",
            "last_event_message",
            "last_transition_reason",
        }
        missing = expected_keys - set(diag.keys())
        assert not missing, f"Missing diagnostic keys: {missing}"

    async def test_diagnostic_data_reflects_current_state(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Diagnostic data 'current_state' matches the forced state."""
        harness.force_state(STATE_MANUAL)

        # Start extended timer so it shows up in diagnostics
        from custom_components.motion_lights_automation.timer_manager import TimerType

        harness.coordinator.timer_manager.start_timer(
            "extended",
            TimerType.EXTENDED,
            harness.coordinator._async_timer_expired,
        )

        diag = harness.coordinator.get_diagnostic_data()
        assert diag["current_state"] == STATE_MANUAL

        # Timer info should have the extended timer
        timers = diag.get("timers", {})
        assert "extended" in timers, f"Expected 'extended' in timers, got: {timers}"


# ===================================================================
# TestCleanup
# ===================================================================


class TestCleanup:
    """Verify resource cleanup."""

    async def test_cleanup_cancels_timers(self, hass: HomeAssistant) -> None:
        """Cleanup cancels all active timers."""
        h = await CoordinatorHarness.create(hass)
        try:
            # Generate an active timer
            await h.motion_on()
            await h.motion_off()
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")
        finally:
            await h.cleanup()

        # After cleanup, timer manager should have no active timers
        h.assert_no_active_timers()

    async def test_cleanup_removes_listeners(self, hass: HomeAssistant) -> None:
        """Cleanup removes listeners; a second cleanup does not crash."""
        h = await CoordinatorHarness.create(hass)
        await h.cleanup()
        # Second cleanup should not raise
        await h.cleanup()
