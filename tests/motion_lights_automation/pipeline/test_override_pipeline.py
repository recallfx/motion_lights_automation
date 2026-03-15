"""Pipeline tests for override switch behavior in every state.

Tests the full coordinator pipeline when the override switch is toggled,
verifying state transitions, timer management, event logging, and
interaction with motion and light state.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.motion_lights_automation.const import (
    CONF_MOTION_DELAY,
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
# 1. Override ON from every state
# ===================================================================


class TestOverrideOnFromEveryState:
    """Verify that override ON transitions to OVERRIDDEN from every state."""

    async def test_from_idle(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """IDLE -> override on -> OVERRIDDEN, no timers."""
        override_harness.force_state(STATE_IDLE)
        override_harness.assert_state(STATE_IDLE)

        await override_harness.override_on()

        override_harness.assert_state(STATE_OVERRIDDEN)
        override_harness.assert_no_active_timers()

    async def test_from_auto(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """AUTO -> override on -> OVERRIDDEN, timers cancelled."""
        # Set up AUTO state: light on, motion timer running
        await override_harness.light_on("light.ceiling", brightness=200)
        override_harness.force_state(STATE_AUTO)
        override_harness.assert_state(STATE_AUTO)

        await override_harness.override_on()

        override_harness.assert_state(STATE_OVERRIDDEN)
        override_harness.assert_no_active_timers()

    async def test_from_manual(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """MANUAL -> override on -> OVERRIDDEN, timers cancelled."""
        # Set up MANUAL state: light on, extended timer running
        await override_harness.light_on("light.ceiling", brightness=200)
        override_harness.force_state(STATE_MANUAL)
        override_harness.assert_state(STATE_MANUAL)

        await override_harness.override_on()

        override_harness.assert_state(STATE_OVERRIDDEN)
        override_harness.assert_no_active_timers()

    async def test_from_motion_auto(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """MOTION_AUTO -> override on -> OVERRIDDEN, timers cancelled."""
        await override_harness.light_on("light.ceiling", brightness=200)
        override_harness.force_state(STATE_MOTION_AUTO)
        override_harness.assert_state(STATE_MOTION_AUTO)

        await override_harness.override_on()

        override_harness.assert_state(STATE_OVERRIDDEN)
        override_harness.assert_no_active_timers()

    async def test_from_motion_manual(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """MOTION_MANUAL -> override on -> OVERRIDDEN, timers cancelled."""
        await override_harness.light_on("light.ceiling", brightness=200)
        override_harness.force_state(STATE_MOTION_MANUAL)
        override_harness.assert_state(STATE_MOTION_MANUAL)

        await override_harness.override_on()

        override_harness.assert_state(STATE_OVERRIDDEN)
        override_harness.assert_no_active_timers()

    async def test_from_manual_off(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """MANUAL_OFF -> override on -> OVERRIDDEN, timers cancelled."""
        await override_harness.light_off("light.ceiling")
        override_harness.force_state(STATE_MANUAL_OFF)
        override_harness.assert_state(STATE_MANUAL_OFF)

        await override_harness.override_on()

        override_harness.assert_state(STATE_OVERRIDDEN)
        override_harness.assert_no_active_timers()

    async def test_from_overridden_stays(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """Already OVERRIDDEN -> override on again -> stays OVERRIDDEN (no double-transition)."""
        override_harness.force_state(STATE_OVERRIDDEN)
        override_harness.assert_state(STATE_OVERRIDDEN)

        # Triggering override_on when already overridden should not cause issues
        await override_harness.override_on()

        override_harness.assert_state(STATE_OVERRIDDEN)

    async def test_logs_automation_overridden(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """Override on logs an 'overridden' event."""
        override_harness.force_state(STATE_IDLE)
        override_harness.clear_event_log()

        await override_harness.override_on()

        override_harness.assert_state(STATE_OVERRIDDEN)
        override_harness.assert_event_log_contains("overridden")


# ===================================================================
# 2. Override OFF with lights on
# ===================================================================


class TestOverrideOffWithLightsOn:
    """Override released while lights are on should go to MANUAL."""

    async def test_override_off_lights_on_goes_to_manual(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """OVERRIDDEN -> lights on -> override off -> MANUAL."""
        # Enter OVERRIDDEN via the real switch so the entity state is "on"
        await override_harness.override_on()
        override_harness.assert_state(STATE_OVERRIDDEN)

        await override_harness.light_on("light.ceiling", brightness=200)
        override_harness.refresh_lights()

        await override_harness.override_off()

        override_harness.assert_state(STATE_MANUAL)

    async def test_override_off_starts_extended_timer(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """Override off with lights on starts the extended timer."""
        await override_harness.override_on()
        override_harness.assert_state(STATE_OVERRIDDEN)

        await override_harness.light_on("light.ceiling", brightness=200)
        override_harness.refresh_lights()

        await override_harness.override_off()

        override_harness.assert_state(STATE_MANUAL)
        override_harness.assert_timer_active("extended")


# ===================================================================
# 3. Override OFF with lights off
# ===================================================================


class TestOverrideOffWithLightsOff:
    """Override released while lights are off should go to IDLE."""

    async def test_override_off_lights_off_goes_to_idle(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """OVERRIDDEN -> lights off -> override off -> IDLE."""
        # Enter OVERRIDDEN via the real switch so the entity state is "on"
        await override_harness.override_on()
        override_harness.assert_state(STATE_OVERRIDDEN)

        await override_harness.light_off("light.ceiling")
        override_harness.refresh_lights()

        await override_harness.override_off()

        override_harness.assert_state(STATE_IDLE)

    async def test_override_off_logs_event(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """Override off logs an event about the release."""
        # Enter OVERRIDDEN via the real switch so the entity state is "on"
        await override_harness.override_on()
        override_harness.assert_state(STATE_OVERRIDDEN)

        await override_harness.light_off("light.ceiling")
        override_harness.refresh_lights()
        override_harness.clear_event_log()

        await override_harness.override_off()

        override_harness.assert_state(STATE_IDLE)
        override_harness.assert_event_log_contains("override released")


# ===================================================================
# 4. Override with motion interaction
# ===================================================================


class TestOverrideWithMotionInteraction:
    """Motion events during override should be ignored."""

    async def test_motion_during_override_ignored(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """Motion on while OVERRIDDEN should not change state."""
        override_harness.force_state(STATE_OVERRIDDEN)
        override_harness.assert_state(STATE_OVERRIDDEN)

        await override_harness.motion_on()

        override_harness.assert_state(STATE_OVERRIDDEN)

    async def test_override_on_cancels_motion_delay(self, hass: HomeAssistant) -> None:
        """Override on during motion delay cancels the delay timer."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_OVERRIDE_SWITCH: "switch.override",
                CONF_MOTION_DELAY: 5,
            },
        )
        try:
            h.assert_state(STATE_IDLE)

            # Motion triggers the delay timer
            await h.motion_on()
            h.assert_timer_active("motion_delay")

            # Override on should cancel all timers including motion_delay
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)
            h.assert_no_active_timers()
        finally:
            await h.cleanup()


# ===================================================================
# 5. Full override cycle
# ===================================================================


class TestOverrideFullCycle:
    """End-to-end override cycles through multiple states."""

    async def test_idle_override_on_off_back_to_idle(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """IDLE -> override on -> OVERRIDDEN -> override off (lights off) -> IDLE."""
        override_harness.assert_state(STATE_IDLE)

        # Override on
        await override_harness.override_on()
        override_harness.assert_state(STATE_OVERRIDDEN)

        # Lights stay off, override off -> IDLE
        override_harness.refresh_lights()
        await override_harness.override_off()
        override_harness.assert_state(STATE_IDLE)

    async def test_motion_auto_override_on_off_to_manual(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """MOTION_AUTO with lights on -> override on -> OVERRIDDEN -> override off -> MANUAL."""
        # Get into MOTION_AUTO with lights on
        await override_harness.motion_on()
        override_harness.assert_state(STATE_MOTION_AUTO)
        # Lights are turned on by the coordinator entering MOTION_AUTO
        await override_harness.light_on("light.ceiling", brightness=200)

        # Override on
        await override_harness.override_on()
        override_harness.assert_state(STATE_OVERRIDDEN)
        override_harness.assert_no_active_timers()

        # Override off with lights still on -> MANUAL
        override_harness.refresh_lights()
        await override_harness.override_off()
        override_harness.assert_state(STATE_MANUAL)
        override_harness.assert_timer_active("extended")

    async def test_override_cycle_preserves_light_state(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """Override on/off does not change light states, just disables automation."""
        # Turn on a light manually
        await override_harness.light_on("light.ceiling", brightness=150)
        override_harness.refresh_lights()
        override_harness.assert_lights_on()

        # Force to a known state with lights on
        override_harness.force_state(STATE_MANUAL)

        # Override on - lights should still be on
        await override_harness.override_on()
        override_harness.assert_state(STATE_OVERRIDDEN)
        override_harness.assert_lights_on()

        # Override off - lights should still be on
        override_harness.refresh_lights()
        await override_harness.override_off()
        override_harness.assert_state(STATE_MANUAL)
        override_harness.assert_lights_on()


# ===================================================================
# 6. No override switch configured
# ===================================================================


class TestNoOverrideSwitchConfigured:
    """Verify coordinator works normally without an override switch."""

    async def test_no_override_switch_no_crash(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Coordinator without override switch should operate normally."""
        harness.assert_state(STATE_IDLE)

        # Normal motion cycle works
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        await harness.motion_off()
        harness.assert_state(STATE_AUTO)
        harness.assert_timer_active("motion")
