"""Tests for KNX resilience features.

Covers:
- Pending command tracking (late KNX confirmations)
- Motion watchdog (stuck motion sensors)
- Periodic state reconciliation (drift from missed events)
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.motion_lights_automation.light_controller import PendingCommand
from custom_components.motion_lights_automation.state_machine import (
    STATE_AUTO,
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MOTION_AUTO,
    STATE_MOTION_MANUAL,
)

from .conftest import CoordinatorHarness


# ========================================================================
# Pending Command Tracking (Late KNX Confirmations)
# ========================================================================


class TestPendingCommandTracking:
    """Test that late KNX confirmations are not treated as manual intervention."""

    async def test_late_knx_confirmation_not_treated_as_manual(
        self, hass: HomeAssistant
    ) -> None:
        """When KNX confirms a light change with its own context, it should not
        be treated as manual intervention."""
        harness = await CoordinatorHarness.create(hass)

        # Motion on → MOTION_AUTO → lights turn on
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        # Simulate: our integration commanded the light on (pending command recorded),
        # then KNX confirms with a different context (not is_integration_context)
        # The is_expected_state_change check should catch this
        lc = harness.coordinator.light_controller
        from homeassistant.util import dt as dt_util

        lc._pending_commands["light.ceiling"] = PendingCommand(
            target_state="on",
            commanded_at=dt_util.now(),
            context_id="some-old-context",
        )

        # Simulate light turning on via KNX (different context)
        # This should be caught by pending command tracking, not flagged as manual
        with patch.object(lc, "is_integration_context", return_value=False):
            hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})
            await hass.async_block_till_done()

        # Should still be in MOTION_AUTO, not MOTION_MANUAL
        harness.assert_state(STATE_MOTION_AUTO)
        await harness.cleanup()

    async def test_pending_command_expires_after_ttl(self, hass: HomeAssistant) -> None:
        """Pending commands older than TTL should not match."""
        harness = await CoordinatorHarness.create(hass)
        lc = harness.coordinator.light_controller

        from datetime import timedelta

        from homeassistant.util import dt as dt_util

        # Record a pending command that's 60 seconds old (past 30s TTL)
        lc._pending_commands["light.ceiling"] = PendingCommand(
            target_state="on",
            commanded_at=dt_util.now() - timedelta(seconds=60),
            context_id="old-context",
        )

        # Should NOT match — too old
        assert not lc.is_expected_state_change("light.ceiling", "on")
        # Should have been cleaned up
        assert "light.ceiling" not in lc._pending_commands
        await harness.cleanup()

    async def test_pending_command_wrong_state_does_not_match(
        self, hass: HomeAssistant
    ) -> None:
        """Pending command for 'on' should not match a state change to 'off'."""
        harness = await CoordinatorHarness.create(hass)
        lc = harness.coordinator.light_controller

        from homeassistant.util import dt as dt_util

        lc._pending_commands["light.ceiling"] = PendingCommand(
            target_state="on",
            commanded_at=dt_util.now(),
            context_id="some-context",
        )

        # 'off' should not match a pending 'on' command
        assert not lc.is_expected_state_change("light.ceiling", "off")
        await harness.cleanup()

    async def test_pending_command_consumed_on_match(self, hass: HomeAssistant) -> None:
        """Matching a pending command should consume it (one-shot)."""
        harness = await CoordinatorHarness.create(hass)
        lc = harness.coordinator.light_controller

        from homeassistant.util import dt as dt_util

        lc._pending_commands["light.ceiling"] = PendingCommand(
            target_state="on",
            commanded_at=dt_util.now(),
            context_id="some-context",
        )

        assert lc.is_expected_state_change("light.ceiling", "on")
        # Second call should not match — already consumed
        assert not lc.is_expected_state_change("light.ceiling", "on")
        await harness.cleanup()


# ========================================================================
# Motion Watchdog
# ========================================================================


class TestMotionWatchdog:
    """Test watchdog that detects stuck motion sensors."""

    async def test_watchdog_starts_in_motion_auto(self, hass: HomeAssistant) -> None:
        """Watchdog should start when entering MOTION_AUTO."""
        harness = await CoordinatorHarness.create(hass)
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        assert harness.coordinator._motion_watchdog_handle is not None
        await harness.cleanup()

    async def test_watchdog_starts_in_motion_manual(self, hass: HomeAssistant) -> None:
        """Watchdog should start when entering MOTION_MANUAL."""
        harness = await CoordinatorHarness.create(hass)
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        # Manual intervention → MOTION_MANUAL
        await harness.manual_light_on(brightness=100)
        harness.assert_state(STATE_MOTION_MANUAL)

        assert harness.coordinator._motion_watchdog_handle is not None
        await harness.cleanup()

    async def test_watchdog_cancelled_on_auto(self, hass: HomeAssistant) -> None:
        """Watchdog should be cancelled when transitioning to AUTO."""
        harness = await CoordinatorHarness.create(hass)
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)
        assert harness.coordinator._motion_watchdog_handle is not None

        await harness.motion_off()
        harness.assert_state(STATE_AUTO)
        assert harness.coordinator._motion_watchdog_handle is None
        await harness.cleanup()

    async def test_watchdog_cancelled_on_idle(self, hass: HomeAssistant) -> None:
        """Watchdog should be cancelled when transitioning to IDLE."""
        harness = await CoordinatorHarness.create(hass)
        await harness.motion_on()
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)

        await harness.expire_timer("motion")
        harness.assert_state(STATE_IDLE)
        assert harness.coordinator._motion_watchdog_handle is None
        await harness.cleanup()

    async def test_watchdog_fires_sensor_off_triggers_motion_off(
        self, hass: HomeAssistant
    ) -> None:
        """When watchdog fires and sensor shows off, trigger motion_off."""
        harness = await CoordinatorHarness.create(hass)
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        # Set motion sensor to off (simulating missed event)
        hass.states.async_set("binary_sensor.motion", "off")
        # Don't call async_block_till_done — we want the state set but
        # NOT to trigger the listener (simulating a missed event scenario)

        # Fire the watchdog callback directly
        await harness.coordinator._async_motion_watchdog_fired()

        # Should have transitioned out of MOTION_AUTO
        harness.assert_state(STATE_AUTO)
        harness.assert_event_log_contains("Watchdog")
        await harness.cleanup()

    async def test_watchdog_fires_sensor_still_on_restarts(
        self, hass: HomeAssistant
    ) -> None:
        """When watchdog fires and sensor still shows on, restart watchdog."""
        harness = await CoordinatorHarness.create(hass)
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        # Sensor still on
        assert hass.states.get("binary_sensor.motion").state == "on"

        # Fire the watchdog
        await harness.coordinator._async_motion_watchdog_fired()

        # Should still be in MOTION_AUTO, watchdog restarted
        harness.assert_state(STATE_MOTION_AUTO)
        assert harness.coordinator._motion_watchdog_handle is not None
        await harness.cleanup()

    async def test_watchdog_fires_in_motion_manual_sensor_off(
        self, hass: HomeAssistant
    ) -> None:
        """Watchdog in MOTION_MANUAL with sensor off triggers motion_off → MANUAL."""
        harness = await CoordinatorHarness.create(hass)
        await harness.motion_on()
        await harness.manual_light_on(brightness=100)
        harness.assert_state(STATE_MOTION_MANUAL)

        # Set sensor to off (missed event)
        hass.states.async_set("binary_sensor.motion", "off")

        await harness.coordinator._async_motion_watchdog_fired()

        # MOTION_MANUAL + motion_off → MANUAL
        harness.assert_state(STATE_MANUAL)
        await harness.cleanup()

    async def test_watchdog_noop_if_not_in_motion_state(
        self, hass: HomeAssistant
    ) -> None:
        """Watchdog should do nothing if state already left MOTION states."""
        harness = await CoordinatorHarness.create(hass)
        harness.assert_state(STATE_IDLE)

        # Fire watchdog while in IDLE — should be a no-op
        await harness.coordinator._async_motion_watchdog_fired()
        harness.assert_state(STATE_IDLE)
        await harness.cleanup()


# ========================================================================
# Periodic State Reconciliation
# ========================================================================


class TestReconciliation:
    """Test periodic state reconciliation catches drift from missed events."""

    async def test_reconciliation_lights_on_state_but_actually_off(
        self, hass: HomeAssistant
    ) -> None:
        """If in AUTO but all lights are actually off, reconcile to IDLE."""
        harness = await CoordinatorHarness.create(hass)

        # Force state to AUTO with lights off
        harness.force_state(STATE_AUTO)
        hass.states.async_set("light.ceiling", "off")

        await harness.coordinator._async_reconcile_state()

        harness.assert_state(STATE_IDLE)
        harness.assert_event_log_contains("Reconciliation")
        await harness.cleanup()

    async def test_reconciliation_idle_but_lights_on(self, hass: HomeAssistant) -> None:
        """If in IDLE but lights are on, reconcile to MANUAL."""
        harness = await CoordinatorHarness.create(hass)
        harness.assert_state(STATE_IDLE)

        # Set lights on without triggering normal listener
        hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})

        # Force state back to IDLE
        harness.force_state(STATE_IDLE)

        await harness.coordinator._async_reconcile_state()

        harness.assert_state(STATE_MANUAL)
        harness.assert_event_log_contains("Reconciliation")
        await harness.cleanup()

    async def test_reconciliation_consistent_state_no_change(
        self, hass: HomeAssistant
    ) -> None:
        """If state is consistent, reconciliation should not change anything."""
        harness = await CoordinatorHarness.create(hass)
        harness.assert_state(STATE_IDLE)

        # Lights are off, state is IDLE — consistent
        await harness.coordinator._async_reconcile_state()
        harness.assert_state(STATE_IDLE)
        await harness.cleanup()

    async def test_reconciliation_motion_auto_consistent(
        self, hass: HomeAssistant
    ) -> None:
        """MOTION_AUTO with motion on and lights on is consistent."""
        harness = await CoordinatorHarness.create(hass)
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        # Lights are on, motion is on — consistent
        await harness.light_on()
        await harness.coordinator._async_reconcile_state()
        harness.assert_state(STATE_MOTION_AUTO)
        await harness.cleanup()

    async def test_reconciliation_manual_lights_off_drift(
        self, hass: HomeAssistant
    ) -> None:
        """If in MANUAL but all lights are actually off, reconcile to IDLE."""
        harness = await CoordinatorHarness.create(hass)

        # Force state to MANUAL with lights off
        harness.force_state(STATE_MANUAL)
        hass.states.async_set("light.ceiling", "off")

        await harness.coordinator._async_reconcile_state()

        harness.assert_state(STATE_IDLE)
        await harness.cleanup()

    async def test_reconciliation_scheduled_on_setup(self, hass: HomeAssistant) -> None:
        """Reconciliation should be scheduled during setup."""
        harness = await CoordinatorHarness.create(hass)
        assert harness.coordinator._reconciliation_handle is not None
        await harness.cleanup()

    async def test_reconciliation_cancelled_on_cleanup(
        self, hass: HomeAssistant
    ) -> None:
        """Reconciliation handle should be cancelled during cleanup."""
        harness = await CoordinatorHarness.create(hass)
        assert harness.coordinator._reconciliation_handle is not None

        await harness.cleanup()
        assert harness.coordinator._reconciliation_handle is None


# ========================================================================
# Multi-sensor motion watchdog
# ========================================================================


class TestMultiSensorWatchdog:
    """Test watchdog with multiple motion sensors."""

    async def test_watchdog_any_sensor_on_keeps_motion(
        self, hass: HomeAssistant
    ) -> None:
        """If any motion sensor still shows on, watchdog should restart."""
        from custom_components.motion_lights_automation.const import CONF_MOTION_ENTITY

        harness = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: [
                    "binary_sensor.motion1",
                    "binary_sensor.motion2",
                ],
            },
        )

        # Trigger motion on sensor 1
        await harness.motion_on("binary_sensor.motion1")
        harness.assert_state(STATE_MOTION_AUTO)

        # Sensor 1 stuck on, sensor 2 off
        hass.states.async_set("binary_sensor.motion1", "on")
        hass.states.async_set("binary_sensor.motion2", "off")

        await harness.coordinator._async_motion_watchdog_fired()

        # Should still be in MOTION_AUTO — sensor 1 is still on
        harness.assert_state(STATE_MOTION_AUTO)
        assert harness.coordinator._motion_watchdog_handle is not None
        await harness.cleanup()

    async def test_watchdog_all_sensors_off_triggers_correction(
        self, hass: HomeAssistant
    ) -> None:
        """If all motion sensors show off, watchdog should trigger motion_off."""
        from custom_components.motion_lights_automation.const import CONF_MOTION_ENTITY

        harness = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: [
                    "binary_sensor.motion1",
                    "binary_sensor.motion2",
                ],
            },
        )

        await harness.motion_on("binary_sensor.motion1")
        harness.assert_state(STATE_MOTION_AUTO)

        # Both sensors off (missed events)
        hass.states.async_set("binary_sensor.motion1", "off")
        hass.states.async_set("binary_sensor.motion2", "off")

        await harness.coordinator._async_motion_watchdog_fired()

        harness.assert_state(STATE_AUTO)
        harness.assert_event_log_contains("Watchdog")
        await harness.cleanup()
