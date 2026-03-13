"""Pipeline tests for timer lifecycle, cancellation, and interactions.

Validates that timers start, expire, cancel, and restart correctly
as the coordinator moves through state transitions.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

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
# TestTimerLifecycle
# ===================================================================


class TestTimerLifecycle:
    """Verify that timers start and expire at the right state boundaries."""

    async def test_motion_timer_starts_on_enter_auto(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """motion on -> off -> AUTO starts the 'motion' timer."""
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        await harness.motion_off()
        harness.assert_state(STATE_AUTO)
        harness.assert_timer_active("motion")

    async def test_motion_timer_expires_to_idle(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """AUTO -> expire 'motion' -> IDLE."""
        await harness.motion_on()
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)

        await harness.expire_timer("motion")
        harness.assert_state(STATE_IDLE)

    async def test_extended_timer_starts_on_enter_manual(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """IDLE -> manual light on -> MANUAL starts the 'extended' timer."""
        harness.force_state(STATE_IDLE)

        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)
        harness.assert_timer_active("extended")

    async def test_extended_timer_expires_to_idle(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """MANUAL -> expire 'extended' -> IDLE."""
        harness.force_state(STATE_IDLE)
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)

        await harness.expire_timer("extended")
        harness.assert_state(STATE_IDLE)

    async def test_manual_off_starts_extended_timer(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """AUTO with light on -> manual light off -> MANUAL_OFF starts 'extended' timer."""
        harness.force_state(STATE_AUTO)
        await harness.light_on("light.ceiling", brightness=200)
        harness.refresh_lights()

        await harness.manual_light_off("light.ceiling")
        harness.assert_state(STATE_MANUAL_OFF)
        harness.assert_timer_active("extended")

    async def test_manual_off_timer_expires_to_idle(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """MANUAL_OFF -> expire 'extended' -> IDLE."""
        harness.force_state(STATE_AUTO)
        await harness.light_on("light.ceiling", brightness=200)
        harness.refresh_lights()

        await harness.manual_light_off("light.ceiling")
        harness.assert_state(STATE_MANUAL_OFF)

        await harness.expire_timer("extended")
        harness.assert_state(STATE_IDLE)


# ===================================================================
# TestTimerCancellation
# ===================================================================


class TestTimerCancellation:
    """Verify that timers are cancelled when appropriate."""

    async def test_motion_on_cancels_auto_timer(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Motion returning in AUTO cancels the motion timer and enters MOTION_AUTO."""
        # Get into AUTO with an active motion timer
        await harness.motion_on()
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)
        harness.assert_timer_active("motion")

        # Motion returns - timer should be cancelled
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)
        harness.assert_timer_inactive("motion")

    async def test_entering_motion_manual_cancels_all_timers(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Transitioning to MOTION_MANUAL cancels all timers."""
        # Get into MOTION_AUTO first
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        # Set a light on so we can do a manual brightness change
        await harness.light_on("light.ceiling", brightness=200)
        harness.refresh_lights()

        # Manual intervention moves to MOTION_MANUAL
        await harness.manual_brightness_change("light.ceiling", brightness=100)
        harness.assert_state(STATE_MOTION_MANUAL)
        harness.assert_no_active_timers()

    async def test_override_on_cancels_all_timers(
        self, hass: HomeAssistant, override_harness: CoordinatorHarness
    ) -> None:
        """Override ON cancels all active timers."""
        h = override_harness

        # Get into AUTO with an active timer
        await h.motion_on()
        await h.motion_off()
        h.assert_state(STATE_AUTO)
        h.assert_timer_active("motion")

        # Override on - all timers should be cancelled
        await h.override_on()
        h.assert_state(STATE_OVERRIDDEN)
        h.assert_no_active_timers()


# ===================================================================
# TestTimerInteractions
# ===================================================================


class TestTimerInteractions:
    """Verify timer restart/reset behavior on user interactions."""

    async def test_manual_brightness_restarts_extended_timer(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Brightness change in MANUAL restarts the extended timer (state stays MANUAL)."""
        harness.force_state(STATE_IDLE)
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)
        harness.assert_timer_active("extended")

        # Brightness change should restart the extended timer, staying in MANUAL
        await harness.manual_brightness_change("light.ceiling", brightness=100)
        harness.assert_state(STATE_MANUAL)
        harness.assert_timer_active("extended")

    async def test_motion_off_in_manual_off_restarts_extended(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Motion clearing in MANUAL_OFF restarts the extended timer."""
        # Get to MANUAL_OFF
        harness.force_state(STATE_AUTO)
        await harness.light_on("light.ceiling", brightness=200)
        harness.refresh_lights()
        await harness.manual_light_off("light.ceiling")
        harness.assert_state(STATE_MANUAL_OFF)
        harness.assert_timer_active("extended")

        # Motion on pauses the timer in MANUAL_OFF
        await harness.motion_on()
        harness.assert_state(STATE_MANUAL_OFF)

        # Motion off should restart the extended timer
        await harness.motion_off()
        harness.assert_state(STATE_MANUAL_OFF)
        harness.assert_timer_active("extended")

    async def test_timer_expired_in_wrong_state_ignored(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Timer expiry in a state that doesn't accept TIMER_EXPIRED is ignored."""
        # Force to MOTION_AUTO (timer expired is NOT valid from this state)
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        # Try to expire a timer - should be silently ignored
        await harness.expire_timer("motion")
        harness.assert_state(STATE_MOTION_AUTO)
