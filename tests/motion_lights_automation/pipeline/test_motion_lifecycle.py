"""Tests for complete motion detection lifecycle scenarios.

Tests the full coordinator pipeline from motion sensor events through state
transitions, timer management, and light control.
"""

from custom_components.motion_lights_automation.const import (
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_DELAY,
    CONF_MOTION_ENTITY,
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

from .conftest import CoordinatorHarness


# ============================================================================
# Basic motion cycle
# ============================================================================


class TestBasicMotionCycle:
    """Test standard motion on/off/timer lifecycle."""

    async def test_idle_motion_on_goes_to_motion_auto(self, harness):
        """Motion detected from IDLE transitions to MOTION_AUTO."""
        harness.assert_state(STATE_IDLE)
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

    async def test_motion_auto_motion_off_goes_to_auto(self, harness):
        """Motion cleared from MOTION_AUTO transitions to AUTO."""
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        await harness.motion_off()
        harness.assert_state(STATE_AUTO)

    async def test_auto_timer_expired_goes_to_idle(self, harness):
        """Timer expiry from AUTO transitions to IDLE."""
        await harness.motion_on()
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)

        await harness.expire_timer("motion")
        harness.assert_state(STATE_IDLE)

    async def test_full_cycle_idle_to_idle(self, harness):
        """Complete cycle: IDLE -> motion on -> motion off -> timer -> IDLE."""
        harness.assert_state(STATE_IDLE)

        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        await harness.motion_off()
        harness.assert_state(STATE_AUTO)
        harness.assert_timer_active("motion")

        await harness.expire_timer("motion")
        harness.assert_state(STATE_IDLE)

    async def test_repeated_motion_extends_cycle(self, harness):
        """Motion re-detected during AUTO resets the cycle."""
        # First motion cycle
        await harness.motion_on()
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)

        # Motion again during AUTO
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        # Clear and let timer expire
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)

        await harness.expire_timer("motion")
        harness.assert_state(STATE_IDLE)

    async def test_motion_on_during_auto_cancels_timer(self, harness):
        """Motion re-detected during AUTO cancels the no-motion timer."""
        await harness.motion_on()
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)
        harness.assert_timer_active("motion")

        # Motion detected again - timer should be cancelled
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)
        harness.assert_timer_inactive("motion")

        # When motion clears, a new timer is started
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)
        harness.assert_timer_active("motion")


# ============================================================================
# Disabled motion activation
# ============================================================================


class TestMotionWithDisabledActivation:
    """Test behavior when CONF_MOTION_ACTIVATION is False.

    Motion activation disabled means motion events do not trigger lights from
    IDLE or MANUAL_OFF states. However, other state transitions (like
    MANUAL -> MOTION_MANUAL) still occur because the coordinator handles
    those states before checking the motion_activation flag.
    """

    async def test_motion_does_not_activate_from_idle(self, hass):
        """Motion in IDLE with activation disabled does not turn on lights."""
        h = await CoordinatorHarness.create(
            hass, config_data={CONF_MOTION_ACTIVATION: False}
        )
        try:
            h.assert_state(STATE_IDLE)
            await h.motion_on()
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_motion_does_not_activate_from_manual_off(self, hass):
        """Motion in MANUAL_OFF with activation disabled stays in MANUAL_OFF."""
        h = await CoordinatorHarness.create(
            hass, config_data={CONF_MOTION_ACTIVATION: False}
        )
        try:
            h.force_state(STATE_MANUAL_OFF)
            await h.motion_on()
            h.assert_state(STATE_MANUAL_OFF)
        finally:
            await h.cleanup()

    async def test_manual_state_transitions_with_activation_disabled(self, hass):
        """MANUAL + motion on still transitions to MOTION_MANUAL even when
        activation is disabled because the coordinator processes MANUAL state
        before checking the motion_activation flag."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={CONF_MOTION_ACTIVATION: False},
        )
        try:
            h.assert_state(STATE_IDLE)

            # Manually turn on a light to get into MANUAL state
            await h.manual_light_on("light.ceiling", brightness=200)
            h.assert_state(STATE_MANUAL)

            # Motion on transitions to MOTION_MANUAL regardless of activation flag
            await h.motion_on()
            h.assert_state(STATE_MOTION_MANUAL)
        finally:
            await h.cleanup()


# ============================================================================
# Motion delay
# ============================================================================


class TestMotionDelay:
    """Test motion delay timer behavior (CONF_MOTION_DELAY)."""

    async def test_motion_from_idle_starts_delay_timer(self, delay_harness):
        """Motion detected starts the delay timer instead of immediately activating."""
        delay_harness.assert_state(STATE_IDLE)

        await delay_harness.motion_on()
        # State should still be IDLE during delay
        delay_harness.assert_state(STATE_IDLE)
        delay_harness.assert_timer_active("motion_delay")

    async def test_delay_expires_with_motion_still_active(self, delay_harness):
        """When delay expires and motion is still active, lights activate."""
        await delay_harness.motion_on()
        delay_harness.assert_state(STATE_IDLE)

        # Expire the delay timer (motion sensor still on)
        await delay_harness.expire_motion_delay()
        delay_harness.assert_state(STATE_MOTION_AUTO)

    async def test_delay_expires_motion_cleared(self, delay_harness):
        """When motion clears during delay, lights do not activate on expiry."""
        await delay_harness.motion_on()
        delay_harness.assert_state(STATE_IDLE)
        delay_harness.assert_timer_active("motion_delay")

        # Motion clears during delay period - cancels delay timer
        await delay_harness.motion_off()
        delay_harness.assert_timer_inactive("motion_delay")

        # Even if we manually call the delay expiry, motion is not active so
        # no transition occurs
        await delay_harness.expire_motion_delay()
        delay_harness.assert_state(STATE_IDLE)

    async def test_motion_from_manual_off_with_delay(self, hass):
        """Motion in MANUAL_OFF with delay configured starts delay timer."""
        h = await CoordinatorHarness.create(hass, config_data={CONF_MOTION_DELAY: 5})
        try:
            h.force_state(STATE_MANUAL_OFF)

            await h.motion_on()
            # State stays MANUAL_OFF, delay timer starts
            h.assert_state(STATE_MANUAL_OFF)
            h.assert_timer_active("motion_delay")
        finally:
            await h.cleanup()


# ============================================================================
# Multiple motion sensors
# ============================================================================


class TestMultipleMotionSensors:
    """Test behavior with multiple motion sensor entities."""

    async def test_first_sensor_triggers_motion(self, hass):
        """First sensor going on activates motion."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: [
                    "binary_sensor.motion1",
                    "binary_sensor.motion2",
                ],
            },
        )
        try:
            h.assert_state(STATE_IDLE)
            await h.motion_on("binary_sensor.motion1")
            h.assert_state(STATE_MOTION_AUTO)
        finally:
            await h.cleanup()

    async def test_second_sensor_keeps_motion(self, hass):
        """With two sensors on, clearing one keeps motion active."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: [
                    "binary_sensor.motion1",
                    "binary_sensor.motion2",
                ],
            },
        )
        try:
            await h.motion_on("binary_sensor.motion1")
            h.assert_state(STATE_MOTION_AUTO)

            await h.motion_on("binary_sensor.motion2")
            h.assert_state(STATE_MOTION_AUTO)

            # Clear first sensor - second still active, so stay in MOTION_AUTO
            await h.motion_off("binary_sensor.motion1")
            h.assert_state(STATE_MOTION_AUTO)
        finally:
            await h.cleanup()

    async def test_all_sensors_off_triggers_motion_off(self, hass):
        """Clearing all sensors triggers motion off transition."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: [
                    "binary_sensor.motion1",
                    "binary_sensor.motion2",
                ],
            },
        )
        try:
            await h.motion_on("binary_sensor.motion1")
            await h.motion_on("binary_sensor.motion2")
            h.assert_state(STATE_MOTION_AUTO)

            await h.motion_off("binary_sensor.motion1")
            h.assert_state(STATE_MOTION_AUTO)

            await h.motion_off("binary_sensor.motion2")
            h.assert_state(STATE_AUTO)
        finally:
            await h.cleanup()


# ============================================================================
# Motion on from every state
# ============================================================================


class TestMotionInEveryState:
    """Test motion on/off events from every possible state."""

    async def test_motion_on_from_idle(self, harness):
        """IDLE + motion on -> MOTION_AUTO."""
        harness.assert_state(STATE_IDLE)
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

    async def test_motion_on_from_auto(self, harness):
        """AUTO + motion on -> MOTION_AUTO, motion timer cancelled."""
        # Get to AUTO state
        await harness.motion_on()
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)
        harness.assert_timer_active("motion")

        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)
        harness.assert_timer_inactive("motion")

    async def test_motion_on_from_manual(self, harness):
        """MANUAL + motion on -> MOTION_MANUAL."""
        # Get to MANUAL state via manual light on
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)

        await harness.motion_on()
        harness.assert_state(STATE_MOTION_MANUAL)

    async def test_motion_on_from_manual_off_ignored(self, harness):
        """MANUAL_OFF + motion on -> stays MANUAL_OFF.

        The state machine defines MANUAL_OFF + MOTION_ON -> MANUAL_OFF which
        is a self-loop (no actual transition). The extended timer is cancelled
        while user is present but state does not change.
        """
        harness.force_state(STATE_MANUAL_OFF)

        await harness.motion_on()
        harness.assert_state(STATE_MANUAL_OFF)

    async def test_motion_on_from_overridden_no_effect(self, hass):
        """OVERRIDDEN + motion on -> stays OVERRIDDEN."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={CONF_OVERRIDE_SWITCH: "switch.override"},
        )
        try:
            h.force_state(STATE_OVERRIDDEN)

            await h.motion_on()
            h.assert_state(STATE_OVERRIDDEN)
        finally:
            await h.cleanup()

    async def test_motion_off_from_motion_auto(self, harness):
        """MOTION_AUTO + motion off -> AUTO with motion timer started."""
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        await harness.motion_off()
        harness.assert_state(STATE_AUTO)
        harness.assert_timer_active("motion")

    async def test_motion_off_from_motion_manual(self, harness):
        """MOTION_MANUAL + motion off -> MANUAL with extended timer started."""
        # Get to MOTION_MANUAL: manual light on -> MANUAL, then motion on
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)

        await harness.motion_on()
        harness.assert_state(STATE_MOTION_MANUAL)

        await harness.motion_off()
        harness.assert_state(STATE_MANUAL)
        harness.assert_timer_active("extended")

    async def test_motion_off_from_manual_off_restarts_timer(self, harness):
        """MANUAL_OFF + motion off -> restarts extended timer."""
        harness.force_state(STATE_MANUAL_OFF)

        # Motion on cancels the extended timer
        await harness.motion_on()
        harness.assert_state(STATE_MANUAL_OFF)

        # Motion off restarts the extended timer
        await harness.motion_off()
        harness.assert_state(STATE_MANUAL_OFF)
        harness.assert_timer_active("extended")


# ============================================================================
# Timer expiry from every state
# ============================================================================


class TestTimerExpiryFromEveryState:
    """Test timer expiry behavior from every possible state.

    The coordinator validates the current state before acting on timer expiry.
    Only AUTO, MANUAL, and MANUAL_OFF accept TIMER_EXPIRED.
    """

    async def test_timer_from_auto_goes_to_idle(self, harness):
        """AUTO + timer expired -> IDLE."""
        await harness.motion_on()
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)

        await harness.expire_timer("motion")
        harness.assert_state(STATE_IDLE)

    async def test_timer_from_manual_goes_to_idle(self, harness):
        """MANUAL + timer expired -> IDLE."""
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)

        await harness.expire_timer("extended")
        harness.assert_state(STATE_IDLE)

    async def test_timer_from_manual_off_goes_to_idle(self, harness):
        """MANUAL_OFF + timer expired -> IDLE."""
        harness.force_state(STATE_MANUAL_OFF)

        await harness.expire_timer("extended")
        harness.assert_state(STATE_IDLE)

    async def test_timer_from_motion_auto_ignored(self, harness):
        """MOTION_AUTO + timer expired -> stays MOTION_AUTO.

        Timer expiry is validated against current state before acting.
        MOTION_AUTO is not in the valid set for timer expiry.
        """
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        await harness.expire_timer("motion")
        harness.assert_state(STATE_MOTION_AUTO)

    async def test_timer_from_motion_manual_ignored(self, harness):
        """MOTION_MANUAL + timer expired -> stays MOTION_MANUAL."""
        await harness.manual_light_on("light.ceiling", brightness=200)
        harness.assert_state(STATE_MANUAL)

        await harness.motion_on()
        harness.assert_state(STATE_MOTION_MANUAL)

        await harness.expire_timer("extended")
        harness.assert_state(STATE_MOTION_MANUAL)

    async def test_timer_from_idle_ignored(self, harness):
        """IDLE + timer expired -> stays IDLE."""
        harness.assert_state(STATE_IDLE)

        await harness.expire_timer("motion")
        harness.assert_state(STATE_IDLE)

    async def test_timer_from_overridden_ignored(self, hass):
        """OVERRIDDEN + timer expired -> stays OVERRIDDEN."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={CONF_OVERRIDE_SWITCH: "switch.override"},
        )
        try:
            h.force_state(STATE_OVERRIDDEN)

            await h.expire_timer("motion")
            h.assert_state(STATE_OVERRIDDEN)
        finally:
            await h.cleanup()
