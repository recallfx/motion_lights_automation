"""Pipeline tests for multi-light scenarios.

Validates behavior when the coordinator manages multiple lights:
partial on/off, sequential manual-off, and full motion cycles.
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
)
from tests.motion_lights_automation.pipeline.conftest import CoordinatorHarness


# ===================================================================
# TestMultipleLightStates
# ===================================================================


class TestMultipleLightStates:
    """Verify light-state queries with multiple lights."""

    async def test_one_light_off_others_on_not_all_off(
        self, hass: HomeAssistant, multi_light_harness: CoordinatorHarness
    ) -> None:
        """Turning off one light while others remain on does NOT trigger MANUAL_OFF."""
        h = multi_light_harness

        # Get into MOTION_AUTO with all 3 lights on
        await h.motion_on()
        h.assert_state(STATE_MOTION_AUTO)

        await h.light_on("light.ceiling", brightness=200)
        await h.light_on("light.lamp", brightness=200)
        await h.light_on("light.wall", brightness=200)
        h.refresh_lights()

        # Manually turn off only the ceiling
        await h.manual_light_off("light.ceiling")

        # Should transition to MOTION_MANUAL (manual intervention) not MANUAL_OFF
        # because lamp and wall are still on
        h.assert_state(STATE_MOTION_MANUAL)

    async def test_all_lights_off_triggers_manual_off(
        self, hass: HomeAssistant, multi_light_harness: CoordinatorHarness
    ) -> None:
        """Sequentially turning off all lights triggers MANUAL_OFF."""
        h = multi_light_harness

        # Get into MOTION_AUTO with all 3 lights on
        await h.motion_on()
        h.assert_state(STATE_MOTION_AUTO)

        await h.light_on("light.ceiling", brightness=200)
        await h.light_on("light.lamp", brightness=200)
        await h.light_on("light.wall", brightness=200)
        h.refresh_lights()

        # Manually turn off all three sequentially
        await h.manual_light_off("light.ceiling")
        await h.manual_light_off("light.lamp")
        await h.manual_light_off("light.wall")

        # After the last light is off, should be in MANUAL_OFF
        h.assert_state(STATE_MANUAL_OFF)

    async def test_any_lights_on_with_mixed_states(
        self, hass: HomeAssistant, multi_light_harness: CoordinatorHarness
    ) -> None:
        """any_lights_on returns True when at least one light is on."""
        h = multi_light_harness

        await h.light_on("light.ceiling", brightness=200)
        await h.light_off("light.lamp")
        await h.light_on("light.wall", brightness=150)
        h.refresh_lights()

        assert h.coordinator.light_controller.any_lights_on() is True


# ===================================================================
# TestMultipleLightManualControl
# ===================================================================


class TestMultipleLightManualControl:
    """Verify manual intervention with multiple lights."""

    async def test_manual_off_one_in_auto_transitions_to_manual(
        self, hass: HomeAssistant, multi_light_harness: CoordinatorHarness
    ) -> None:
        """Manually turning off one light in AUTO (some still on) -> MANUAL."""
        h = multi_light_harness

        # Get into AUTO with all lights on
        await h.motion_on()
        await h.motion_off()
        h.assert_state(STATE_AUTO)

        await h.light_on("light.ceiling", brightness=200)
        await h.light_on("light.lamp", brightness=200)
        await h.light_on("light.wall", brightness=200)
        h.refresh_lights()

        # Manually turn off just the ceiling
        await h.manual_light_off("light.ceiling")

        # Some lights still on -> should be MANUAL (not MANUAL_OFF)
        h.assert_state(STATE_MANUAL)

    async def test_manual_off_one_in_manual_restarts_timer(
        self, hass: HomeAssistant, multi_light_harness: CoordinatorHarness
    ) -> None:
        """Manually turning off one light in MANUAL (some still on) restarts timer."""
        h = multi_light_harness

        # Get into MANUAL
        h.force_state(STATE_IDLE)
        await h.manual_light_on("light.ceiling", brightness=200)
        await h.light_on("light.lamp", brightness=200)
        await h.light_on("light.wall", brightness=200)
        h.refresh_lights()

        # Should be in MANUAL with extended timer
        h.assert_state(STATE_MANUAL)
        h.assert_timer_active("extended")

        # Manually turn off lamp (others still on)
        await h.manual_light_off("light.lamp")

        # Should still be MANUAL with restarted timer
        h.assert_state(STATE_MANUAL)
        h.assert_timer_active("extended")


# ===================================================================
# TestMultipleLightTurnOnOff
# ===================================================================


class TestMultipleLightTurnOnOff:
    """Verify full motion cycles with multiple lights."""

    async def test_motion_cycle_with_multiple_lights(
        self, hass: HomeAssistant, multi_light_harness: CoordinatorHarness
    ) -> None:
        """Full motion cycle: motion on -> off -> timer -> IDLE."""
        h = multi_light_harness

        # Motion on triggers MOTION_AUTO (integration will turn on lights via service)
        await h.motion_on()
        h.assert_state(STATE_MOTION_AUTO)

        # Motion clears -> AUTO with motion timer
        await h.motion_off()
        h.assert_state(STATE_AUTO)
        h.assert_timer_active("motion")

        # Timer expires -> IDLE (lights turn off)
        await h.expire_timer("motion")
        h.assert_state(STATE_IDLE)
