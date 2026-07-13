"""Tests for KNX resilience features.

Covers:
- Pending command tracking (late KNX confirmations)
- Motion watchdog (stuck motion sensors)
- Periodic state reconciliation (drift from missed events)
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_HOUSE_ACTIVE,
    CONF_OVERRIDE_SWITCH,
)
from custom_components.motion_lights_automation.light_controller import PendingCommand
from custom_components.motion_lights_automation.state_machine import (
    STATE_AUTO,
    STATE_IDLE,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_MOTION_AUTO,
    STATE_MOTION_MANUAL,
    STATE_OVERRIDDEN,
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

        # Simulate MOTION_AUTO while KNX confirmation is still pending.
        harness.force_state(STATE_MOTION_AUTO)
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
        """Watchdog in MOTION_MANUAL with sensor off triggers motion_off -> IDLE."""
        harness = await CoordinatorHarness.create(hass)
        await harness.motion_on()
        await harness.manual_light_on(brightness=100)
        harness.assert_state(STATE_MOTION_MANUAL)

        # Set sensor to off (missed event)
        hass.states.async_set("binary_sensor.motion", "off")

        await harness.coordinator._async_motion_watchdog_fired()

        harness.assert_state(STATE_IDLE)
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

    async def test_motion_auto_returns_to_idle_when_too_bright(
        self, hass: HomeAssistant
    ) -> None:
        """Bright ambient light should not leave the room stuck in MOTION_AUTO."""
        harness = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_ambient="100",
        )

        await harness.motion_on()

        harness.assert_state(STATE_IDLE)
        harness.assert_lights_off()
        harness.assert_event_log_contains("too bright")
        await harness.cleanup()

    async def test_motion_auto_returns_to_idle_when_inactive_brightness_zero(
        self, hass: HomeAssistant
    ) -> None:
        """Inactive brightness 0 should not leave MOTION_AUTO with no lights on."""
        harness = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
                CONF_BRIGHTNESS_INACTIVE: 0,
            },
            initial_house_active="off",
        )

        await harness.motion_on()

        harness.assert_state(STATE_IDLE)
        harness.assert_lights_off()
        harness.assert_event_log_contains("inactive brightness 0%")
        await harness.cleanup()

    async def test_accepted_command_that_leaves_light_off_returns_to_idle(
        self, harness
    ) -> None:
        """A completed service call is not proof that the light turned on."""
        harness.hass.services.async_remove("light", "turn_on")

        async def accept_without_device_change(call) -> None:
            return None

        harness.hass.services.async_register(
            "light", "turn_on", accept_without_device_change
        )

        with (
            patch(
                "custom_components.motion_lights_automation.motion_coordinator."
                "LIGHT_STATE_CONFIRMATION_DELAY",
                0,
            ),
            patch(
                "custom_components.motion_lights_automation.light_controller."
                "PENDING_COMMAND_TTL_SECONDS",
                0,
            ),
        ):
            await harness.motion_on()

        harness.assert_state(STATE_IDLE)
        harness.assert_lights_off()

    async def test_delayed_confirmation_keeps_motion_auto(self, harness) -> None:
        """A late KNX ON must arrive before failed-command reconciliation."""
        harness.hass.services.async_remove("light", "turn_on")
        command_seen = asyncio.Event()
        release_confirmation = asyncio.Event()

        async def accept_then_confirm_later(call) -> None:
            command_seen.set()

            async def confirm() -> None:
                await release_confirmation.wait()
                harness.hass.states.async_set(
                    "light.ceiling",
                    "on",
                    attributes={"brightness": 204},
                    context=call.context,
                )

            harness.hass.async_create_task(confirm())

        harness.hass.services.async_register(
            "light", "turn_on", accept_then_confirm_later
        )
        harness.force_state(STATE_MOTION_AUTO)

        with patch(
            "custom_components.motion_lights_automation.motion_coordinator."
            "LIGHT_STATE_CONFIRMATION_DELAY",
            0.05,
        ):
            activation = asyncio.create_task(
                harness.coordinator._async_turn_on_lights()
            )
            await command_seen.wait()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            release_confirmation.set()
            await activation
            await harness.hass.async_block_till_done()

        harness.assert_state(STATE_MOTION_AUTO)
        harness.assert_lights_on()

    async def test_confirmation_waits_for_pending_command_lifetime(
        self, harness
    ) -> None:
        """A valid late ON must not outlive activation reconciliation."""
        harness.hass.services.async_remove("light", "turn_on")
        command_seen = asyncio.Event()

        async def accept_then_confirm_after_old_grace(call) -> None:
            command_seen.set()

            async def confirm() -> None:
                await asyncio.sleep(0.05)
                harness.hass.states.async_set(
                    "light.ceiling",
                    "on",
                    attributes={"brightness": 204},
                    context=call.context,
                )

            harness.hass.async_create_task(confirm())

        harness.hass.services.async_register(
            "light", "turn_on", accept_then_confirm_after_old_grace
        )
        harness.force_state(STATE_MOTION_AUTO)

        with (
            patch(
                "custom_components.motion_lights_automation.motion_coordinator."
                "LIGHT_STATE_CONFIRMATION_DELAY",
                0.01,
            ),
            patch(
                "custom_components.motion_lights_automation.light_controller."
                "PENDING_COMMAND_TTL_SECONDS",
                0.2,
            ),
        ):
            activation = asyncio.create_task(
                harness.coordinator._async_turn_on_lights()
            )
            await command_seen.wait()
            await activation
            await harness.hass.async_block_till_done()

        harness.assert_state(STATE_MOTION_AUTO)
        harness.assert_lights_on()

    async def test_override_cancels_slow_activation_before_it_turns_on(
        self, hass: HomeAssistant
    ) -> None:
        """Leaving MOTION_AUTO must stop unfinished activation work."""
        harness = await CoordinatorHarness.create(
            hass,
            config_data={CONF_OVERRIDE_SWITCH: "switch.override"},
        )
        activation_started = asyncio.Event()
        release_activation = asyncio.Event()
        light_turned_on = asyncio.Event()

        async def slow_turn_on(_context) -> list[str]:
            activation_started.set()
            await release_activation.wait()
            light_turned_on.set()
            hass.states.async_set("light.ceiling", "on", attributes={"brightness": 204})
            return ["light.ceiling"]

        try:
            with patch.object(
                harness.coordinator.light_controller,
                "turn_on_auto_lights",
                side_effect=slow_turn_on,
            ):
                harness.coordinator._handle_motion_on()
                await activation_started.wait()

                harness.coordinator._handle_override_on()
                harness.assert_state(STATE_OVERRIDDEN)

                release_activation.set()
                activation = harness.coordinator._activation_task
                if activation is not None:
                    await asyncio.gather(activation, return_exceptions=True)
                await asyncio.sleep(0)

            assert not light_turned_on.is_set()
            harness.assert_lights_off()
        finally:
            release_activation.set()
            await harness.cleanup()

    async def test_manual_off_cancels_slow_activation_before_it_turns_on(
        self, hass: HomeAssistant
    ) -> None:
        """Entering MANUAL_OFF must stop unfinished activation work."""
        harness = await CoordinatorHarness.create(hass, initial_motion="on")
        activation_started = asyncio.Event()
        release_activation = asyncio.Event()
        light_turned_on = asyncio.Event()

        async def slow_turn_on(_context) -> list[str]:
            activation_started.set()
            await release_activation.wait()
            light_turned_on.set()
            hass.states.async_set("light.ceiling", "on", attributes={"brightness": 204})
            return ["light.ceiling"]

        try:
            with patch.object(
                harness.coordinator.light_controller,
                "turn_on_auto_lights",
                side_effect=slow_turn_on,
            ):
                harness.coordinator._handle_motion_on()
                await activation_started.wait()
                activation = harness.coordinator._activation_task
                assert activation is not None

                harness.coordinator._handle_all_lights_manually_off(STATE_MOTION_AUTO)
                harness.assert_state(STATE_MANUAL_OFF)

                release_activation.set()
                await asyncio.gather(activation, return_exceptions=True)

            assert activation.cancelled()
            assert not light_turned_on.is_set()
            harness.assert_lights_off()
        finally:
            release_activation.set()
            await harness.cleanup()

    async def test_failed_activation_does_not_cancel_its_own_task(
        self, harness
    ) -> None:
        """Failed-command reconciliation should complete normally."""
        harness.hass.services.async_remove("light", "turn_on")

        async def accept_without_device_change(call) -> None:
            return None

        harness.hass.services.async_register(
            "light", "turn_on", accept_without_device_change
        )

        with (
            patch(
                "custom_components.motion_lights_automation.motion_coordinator."
                "LIGHT_STATE_CONFIRMATION_DELAY",
                0,
            ),
            patch(
                "custom_components.motion_lights_automation.light_controller."
                "PENDING_COMMAND_TTL_SECONDS",
                0,
            ),
        ):
            harness.coordinator._handle_motion_on()
            activation = harness.coordinator._activation_task
            assert activation is not None
            await activation

        assert not activation.cancelled()
        harness.assert_state(STATE_IDLE)
        harness.assert_lights_off()

    async def test_old_activation_cannot_reset_a_new_motion_visit(
        self, harness
    ) -> None:
        """An older confirmation timeout must not reset a newer visit."""
        harness.hass.services.async_remove("light", "turn_on")
        first_command = asyncio.Event()
        second_command = asyncio.Event()
        command_count = 0

        async def accept_without_confirmation(call) -> None:
            nonlocal command_count
            command_count += 1
            (first_command if command_count == 1 else second_command).set()

        harness.hass.services.async_register(
            "light", "turn_on", accept_without_confirmation
        )

        try:
            with patch(
                "custom_components.motion_lights_automation.motion_coordinator."
                "LIGHT_STATE_CONFIRMATION_DELAY",
                0.5,
            ):
                harness.coordinator._handle_motion_on()
                await first_command.wait()
                await asyncio.sleep(0.2)

                harness.coordinator._handle_motion_off()
                harness.coordinator._handle_motion_on()
                await second_command.wait()
                await asyncio.sleep(0.35)

                harness.assert_state(STATE_MOTION_AUTO)
        finally:
            harness.coordinator.async_cleanup_listeners()
            await asyncio.sleep(0.2)

    async def test_ambient_reactivation_supersedes_older_confirmation(
        self, ambient_harness
    ) -> None:
        """A newer ambient adjustment must supersede an older failed command."""
        ambient_harness.hass.services.async_remove("light", "turn_on")
        first_command = asyncio.Event()
        second_command = asyncio.Event()
        command_count = 0

        async def accept_and_confirm_only_second(call) -> None:
            nonlocal command_count
            command_count += 1
            if command_count == 1:
                first_command.set()
                return

            second_command.set()

            async def confirm() -> None:
                await asyncio.sleep(0.35)
                ambient_harness.hass.states.async_set(
                    "light.ceiling",
                    "on",
                    attributes={"brightness": 204},
                    context=call.context,
                )

            ambient_harness.hass.async_create_task(confirm())

        ambient_harness.hass.services.async_register(
            "light", "turn_on", accept_and_confirm_only_second
        )
        ambient_harness.force_state(STATE_MOTION_AUTO)
        motion_trigger = ambient_harness.coordinator.trigger_manager.get_trigger(
            "motion"
        )
        event = SimpleNamespace(
            data={
                "old_state": SimpleNamespace(state="off", attributes={}),
                "new_state": SimpleNamespace(state="on", attributes={}),
            }
        )
        context = {
            "is_dark_inside": True,
            "is_house_active": True,
            "motion_active": True,
            "current_state": STATE_MOTION_AUTO,
            "all_lights": ["light.ceiling"],
        }

        with (
            patch(
                "custom_components.motion_lights_automation.motion_coordinator."
                "LIGHT_STATE_CONFIRMATION_DELAY",
                0.5,
            ),
            patch.object(motion_trigger, "is_active", return_value=True),
            patch.object(
                ambient_harness.coordinator, "_get_context", return_value=context
            ),
        ):
            first = asyncio.create_task(
                ambient_harness.coordinator._async_ambient_light_changed(event)
            )
            await first_command.wait()
            await asyncio.sleep(0.2)
            second = asyncio.create_task(
                ambient_harness.coordinator._async_ambient_light_changed(event)
            )
            await second_command.wait()
            await asyncio.gather(first, second, return_exceptions=True)

        ambient_harness.assert_state(STATE_MOTION_AUTO)
        ambient_harness.assert_lights_on()

    async def test_cleanup_cancels_pending_activation(self, harness) -> None:
        """An unloaded coordinator cannot finish activation and turn lights off."""
        harness.hass.services.async_remove("light", "turn_on")
        command_seen = asyncio.Event()

        async def accept_without_confirmation(call) -> None:
            command_seen.set()

        harness.hass.services.async_register(
            "light", "turn_on", accept_without_confirmation
        )
        turn_off = AsyncMock()
        harness.coordinator._async_turn_off_lights = turn_off

        with patch(
            "custom_components.motion_lights_automation.motion_coordinator."
            "LIGHT_STATE_CONFIRMATION_DELAY",
            0.2,
        ):
            harness.coordinator._handle_motion_on()
            await command_seen.wait()
            await asyncio.sleep(0)
            harness.coordinator.async_cleanup_listeners()
            await asyncio.sleep(0.25)

        harness.assert_state(STATE_MOTION_AUTO)
        turn_off.assert_not_awaited()

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

    async def test_reconciliation_warning_includes_entry_title(
        self, hass: HomeAssistant, caplog
    ) -> None:
        """Reconciliation warnings should identify the configured room."""
        harness = await CoordinatorHarness.create(hass)

        harness.force_state(STATE_AUTO)
        hass.states.async_set("light.ceiling", "off")

        with caplog.at_level(logging.WARNING):
            await harness.coordinator._async_reconcile_state()

        assert any(
            "Reconciliation for Pipeline Test" in record.message
            and "all lights are off" in record.message
            for record in caplog.records
        )
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
