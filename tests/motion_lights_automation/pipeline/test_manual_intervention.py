"""Pipeline tests for manual user intervention in every possible state.

Tests cover:
- Manual light ON from various states (IDLE, MANUAL_OFF)
- Manual adjustments (brightness change, light off) in every active state
- All-lights-off (integration context) detection from every state
- Startup grace period behavior
"""

from unittest.mock import patch

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


# ======================================================================
# 1. Manual ON from IDLE
# ======================================================================


class TestManualOnFromIdle:
    """Test user manually turning on a light while in IDLE state."""

    async def test_manual_on_transitions_to_manual(self, harness):
        """Turning on a light manually from IDLE should go to MANUAL."""
        harness.force_state(STATE_IDLE)
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)

    async def test_manual_on_starts_extended_timer(self, harness):
        """Manual ON from IDLE should start the extended timer."""
        harness.force_state(STATE_IDLE)
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)
        harness.assert_timer_active("extended")

    async def test_manual_on_logs_event(self, harness):
        """Manual ON from IDLE should log a human-readable event."""
        harness.force_state(STATE_IDLE)
        harness.clear_event_log()
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_event_log_contains("turned on manually")


# ======================================================================
# 2. Manual ON from MANUAL_OFF
# ======================================================================


class TestManualOnFromManualOff:
    """Test user manually turning on a light while in MANUAL_OFF state."""

    async def test_manual_on_transitions_to_manual(self, harness):
        """Turning on a light manually from MANUAL_OFF should go to MANUAL."""
        harness.force_state(STATE_MANUAL_OFF)
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)

    async def test_manual_on_cancels_and_restarts_timer(self, harness):
        """Manual ON from MANUAL_OFF should cancel old timer and start new extended timer."""
        harness.force_state(STATE_MANUAL_OFF)
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)
        # Entering MANUAL starts a fresh extended timer
        harness.assert_timer_active("extended")


# ======================================================================
# 3. Manual adjustment in MOTION_AUTO
# ======================================================================


class TestManualAdjustmentInMotionAuto:
    """Test manual interventions while in MOTION_AUTO state."""

    async def test_brightness_change_transitions_to_motion_manual(self, harness):
        """Changing brightness in MOTION_AUTO should transition to MOTION_MANUAL."""
        harness.force_state(STATE_MOTION_AUTO)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        await harness.manual_brightness_change("light.ceiling", brightness=100)
        harness.assert_state(STATE_MOTION_MANUAL)

    async def test_manual_off_all_lights_transitions_to_manual_off(self, harness):
        """Turning off all lights in MOTION_AUTO should transition to MANUAL_OFF."""
        harness.force_state(STATE_MOTION_AUTO)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        await harness.manual_light_off("light.ceiling")
        harness.assert_state(STATE_MANUAL_OFF)

    async def test_manual_off_some_lights_transitions_to_motion_manual(
        self, multi_light_harness
    ):
        """Turning off one light (others still on) in MOTION_AUTO -> MOTION_MANUAL."""
        h = multi_light_harness
        # Set up two lights on
        h.hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})
        h.hass.states.async_set("light.lamp", "on", attributes={"brightness": 200})
        h.force_state(STATE_MOTION_AUTO)
        h.refresh_lights()

        # Manually turn off just the ceiling — lamp still on
        await h.manual_light_off("light.ceiling")
        h.assert_state(STATE_MOTION_MANUAL)


# ======================================================================
# 4. Manual adjustment in MOTION_MANUAL
# ======================================================================


class TestManualAdjustmentInMotionManual:
    """Test manual interventions while in MOTION_MANUAL state."""

    async def test_manual_off_all_transitions_to_manual_off(self, harness):
        """Turning off all lights in MOTION_MANUAL should go to MANUAL_OFF."""
        harness.force_state(STATE_MOTION_MANUAL)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        await harness.manual_light_off("light.ceiling")
        harness.assert_state(STATE_MANUAL_OFF)

    async def test_brightness_change_stays_in_motion_manual(self, harness):
        """Brightness change in MOTION_MANUAL should stay in MOTION_MANUAL."""
        harness.force_state(STATE_MOTION_MANUAL)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        await harness.manual_brightness_change("light.ceiling", brightness=100)
        harness.assert_state(STATE_MOTION_MANUAL)


# ======================================================================
# 5. Manual adjustment in AUTO
# ======================================================================


class TestManualAdjustmentInAuto:
    """Test manual interventions while in AUTO state."""

    async def test_brightness_change_transitions_to_manual(self, harness):
        """Changing brightness in AUTO should transition to MANUAL."""
        harness.force_state(STATE_AUTO)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        await harness.manual_brightness_change("light.ceiling", brightness=100)
        harness.assert_state(STATE_MANUAL)

    async def test_manual_off_all_transitions_to_manual_off(self, harness):
        """Turning off all lights in AUTO should transition to MANUAL_OFF."""
        harness.force_state(STATE_AUTO)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        await harness.manual_light_off("light.ceiling")
        harness.assert_state(STATE_MANUAL_OFF)

    async def test_manual_off_some_transitions_to_manual(self, multi_light_harness):
        """Turning off one light (others still on) in AUTO -> MANUAL."""
        h = multi_light_harness
        h.hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})
        h.hass.states.async_set("light.lamp", "on", attributes={"brightness": 200})
        h.force_state(STATE_AUTO)
        h.refresh_lights()

        # Manually turn off just ceiling — lamp still on
        await h.manual_light_off("light.ceiling")
        h.assert_state(STATE_MANUAL)


# ======================================================================
# 6. Manual adjustment in MANUAL
# ======================================================================


class TestManualAdjustmentInManual:
    """Test manual interventions while in MANUAL state."""

    async def test_brightness_change_restarts_extended_timer(self, harness):
        """Brightness change in MANUAL should stay in MANUAL and restart timer."""
        harness.force_state(STATE_MANUAL)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        await harness.manual_brightness_change("light.ceiling", brightness=100)
        harness.assert_state(STATE_MANUAL)
        harness.assert_timer_active("extended")

    async def test_manual_off_all_transitions_to_manual_off(self, harness):
        """Turning off all lights in MANUAL should transition to MANUAL_OFF."""
        harness.force_state(STATE_MANUAL)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        await harness.manual_light_off("light.ceiling")
        harness.assert_state(STATE_MANUAL_OFF)

    async def test_manual_off_some_restarts_timer(self, multi_light_harness):
        """Turning off one light (others on) in MANUAL should stay MANUAL and restart timer."""
        h = multi_light_harness
        h.hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})
        h.hass.states.async_set("light.lamp", "on", attributes={"brightness": 200})
        h.force_state(STATE_MANUAL)
        h.refresh_lights()

        # Turn off just ceiling — lamp is still on
        await h.manual_light_off("light.ceiling")
        h.assert_state(STATE_MANUAL)
        h.assert_timer_active("extended")


# ======================================================================
# 7. Manual OFF in MANUAL_OFF
# ======================================================================


class TestManualOffInManualOff:
    """Test manual off interventions while already in MANUAL_OFF state."""

    async def test_another_light_off_restarts_extended_timer(self, multi_light_harness):
        """Turning off another light in MANUAL_OFF should stay and restart timer."""
        h = multi_light_harness
        # One light still on, the other off — simulates partial manual off
        h.hass.states.async_set("light.ceiling", "off")
        h.hass.states.async_set("light.lamp", "on", attributes={"brightness": 200})
        h.force_state(STATE_MANUAL_OFF)
        h.refresh_lights()

        # User turns off the remaining light manually
        await h.manual_light_off("light.lamp")
        h.assert_state(STATE_MANUAL_OFF)
        h.assert_timer_active("extended")


# ======================================================================
# 8. LIGHTS_ALL_OFF event path (integration context, not manual)
# ======================================================================


class TestLightsAllOff:
    """Test the LIGHTS_ALL_OFF event from various states.

    These simulate lights turning off via integration context (not manual),
    e.g., automation turning off lights or timer-based off.
    We patch is_integration_context to return True so the change is
    recognized as integration-controlled rather than manual.
    """

    async def test_all_lights_off_in_auto_goes_to_idle(self, harness):
        """All lights off in AUTO (integration context) should go to IDLE."""
        harness.force_state(STATE_AUTO)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        with patch.object(
            harness.coordinator.light_controller,
            "is_integration_context",
            return_value=True,
        ):
            harness.hass.states.async_set("light.ceiling", "off")
            await harness.hass.async_block_till_done()

        harness.assert_state(STATE_IDLE)

    async def test_all_lights_off_in_manual_goes_to_idle(self, harness):
        """All lights off in MANUAL (integration context) should go to IDLE."""
        harness.force_state(STATE_MANUAL)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        with patch.object(
            harness.coordinator.light_controller,
            "is_integration_context",
            return_value=True,
        ):
            harness.hass.states.async_set("light.ceiling", "off")
            await harness.hass.async_block_till_done()

        harness.assert_state(STATE_IDLE)

    async def test_all_lights_off_in_motion_auto_goes_to_idle(self, harness):
        """All lights off in MOTION_AUTO (integration context) should go to IDLE."""
        harness.force_state(STATE_MOTION_AUTO)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        with patch.object(
            harness.coordinator.light_controller,
            "is_integration_context",
            return_value=True,
        ):
            harness.hass.states.async_set("light.ceiling", "off")
            await harness.hass.async_block_till_done()

        harness.assert_state(STATE_IDLE)

    async def test_all_lights_off_in_motion_manual_goes_to_idle(self, harness):
        """All lights off in MOTION_MANUAL (integration context) should go to IDLE."""
        harness.force_state(STATE_MOTION_MANUAL)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        with patch.object(
            harness.coordinator.light_controller,
            "is_integration_context",
            return_value=True,
        ):
            harness.hass.states.async_set("light.ceiling", "off")
            await harness.hass.async_block_till_done()

        harness.assert_state(STATE_IDLE)

    async def test_all_lights_off_in_overridden_no_transition(self, override_harness):
        """All lights off in OVERRIDDEN should NOT transition (stay OVERRIDDEN)."""
        h = override_harness
        h.force_state(STATE_OVERRIDDEN)
        h.hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})
        h.refresh_lights()

        await h.light_off("light.ceiling")
        h.assert_state(STATE_OVERRIDDEN)

    async def test_all_lights_off_in_manual_off_no_transition(self, harness):
        """All lights off in MANUAL_OFF should NOT transition (stay MANUAL_OFF)."""
        harness.force_state(STATE_MANUAL_OFF)
        harness.hass.states.async_set(
            "light.ceiling", "on", attributes={"brightness": 200}
        )
        harness.refresh_lights()

        await harness.light_off("light.ceiling")
        harness.assert_state(STATE_MANUAL_OFF)


# ======================================================================
# 9. Startup grace period
# ======================================================================


class TestStartupGracePeriod:
    """Test that light changes during the startup grace period are ignored."""

    async def test_light_change_during_grace_period_ignored(self, hass):
        """Light changes during the startup grace period should not trigger transitions."""
        # Start with lights on; coordinator detects lights on and sets AUTO
        h = await CoordinatorHarness.create(
            hass,
            skip_grace_period=False,
            initial_lights={
                "light.ceiling": {"state": "on", "brightness": 200},
            },
        )
        try:
            # Coordinator sets AUTO on startup when lights are on
            initial_state = h.state

            # Manual brightness change during grace period should be ignored
            await h.manual_brightness_change("light.ceiling", brightness=100)

            # State should NOT have changed — grace period blocks manual detection
            h.assert_state(initial_state)
        finally:
            await h.cleanup()
