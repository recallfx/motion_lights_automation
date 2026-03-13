"""Pipeline tests for ambient light sensor behavior across all states.

Tests the full coordinator pipeline when ambient light changes, verifying
hysteresis logic, state transitions, light control, and interaction with
motion and manual states.
"""

from __future__ import annotations

from homeassistant.core import Context, HomeAssistant

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_MOTION_ACTIVATION,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _simulate_integration_light_off(
    harness: CoordinatorHarness,
    entity_id: str = "light.ceiling",
) -> None:
    """Simulate a light turning off as if the integration did it.

    Creates a tracked context so the manual-intervention detector does not
    flag this as a user action.
    """
    ctx = Context()
    harness.coordinator.light_controller._context_tracking.add(ctx.id)
    harness.hass.states.async_set(entity_id, "off", context=ctx)
    await harness.hass.async_block_till_done()


def _make_turn_off_spy(harness: CoordinatorHarness):
    """Return (spy_fn, was_called) pair.

    The spy replaces ``_async_turn_off_lights``, records the call, and
    simulates light(s) going off with a tracked integration context so the
    light-change handler fires ``LIGHTS_ALL_OFF`` instead of
    ``MANUAL_OFF_INTERVENTION``.

    Note: does NOT call ``async_block_till_done`` inside the spy because
    the spy runs inside an event handler; the outer ``async_block_till_done``
    (from ``set_ambient_lux``) will drain all follow-on events.
    """
    called = {"value": False}

    async def spy():
        called["value"] = True
        # Simulate each managed light turning off with integration context.
        # async_set is synchronous and queues state_changed events that will
        # be processed by the already-running async_block_till_done.
        for light_id in harness.coordinator.light_controller.lights:
            ctx = Context()
            harness.coordinator.light_controller._context_tracking.add(ctx.id)
            harness.hass.states.async_set(light_id, "off", context=ctx)

    return spy, called


# ===================================================================
# 1. Lux Hysteresis
# ===================================================================


class TestLuxHysteresis:
    """Verify the +-20 lux hysteresis around the configured threshold.

    Threshold = 50, so:
      - BRIGHT stays bright until lux <= 30
      - DIM stays dim until lux >= 70
    """

    async def test_bright_to_dark_triggers_at_threshold_minus_20(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """Start at 100 lux (bright), decrease to 29 -> becomes dark."""
        # Initial lux is 100 (bright). Turn motion on so trigger reports active.
        # motion_on() transitions IDLE -> MOTION_AUTO, which initializes
        # hysteresis via _get_context() call inside _async_turn_on_lights().
        await ambient_harness.motion_on()
        ambient_harness.assert_state(STATE_MOTION_AUTO)

        # Force back to IDLE. Motion sensor stays "on" so trigger.is_active()=True.
        ambient_harness.force_state(STATE_IDLE)

        # Lux drops to 29 -> below low_threshold (30), should become dark.
        # Ambient handler: old_is_dark=False (100 lux), is_dark_now=True (29 lux).
        # IDLE + motion active + dark -> fires MOTION_ON -> MOTION_AUTO
        await ambient_harness.set_ambient_lux(29)

        ambient_harness.assert_state(STATE_MOTION_AUTO)

    async def test_bright_stays_bright_at_threshold(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """Start at 100 lux (bright), decrease to 50 -> still bright (in hysteresis band)."""
        # Initialize hysteresis (BRIGHT mode) via motion_on
        await ambient_harness.motion_on()
        ambient_harness.force_state(STATE_IDLE)

        await ambient_harness.set_ambient_lux(50)

        # 50 > 30 (low_threshold), so still bright. No darkness change -> stays IDLE.
        ambient_harness.assert_state(STATE_IDLE)

    async def test_bright_stays_bright_at_31(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """Start at 100 lux (bright), decrease to 31 -> still bright (just above 30)."""
        ambient_harness.force_state(STATE_IDLE)

        await ambient_harness.set_ambient_lux(31)

        # 31 > 30 (low_threshold), hysteresis prevents switch. Stays bright.
        ambient_harness.assert_state(STATE_IDLE)

    async def test_dark_to_bright_triggers_at_threshold_plus_20(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """Start dark (10 lux), increase to 71 -> becomes bright."""
        # Get into dark mode
        await ambient_harness.set_ambient_lux(10)

        # Set up AUTO with lights on
        await ambient_harness.light_on("light.ceiling", brightness=200)
        ambient_harness.force_state(STATE_AUTO)

        # Spy on turn_off that simulates lights going off with integration context
        spy, called = _make_turn_off_spy(ambient_harness)
        ambient_harness.coordinator._async_turn_off_lights = spy

        # Increase to 71 -> above high_threshold (70), should become bright
        await ambient_harness.set_ambient_lux(71)
        await hass.async_block_till_done()

        assert called["value"], "Expected _async_turn_off_lights to be called"
        # After lights off -> LIGHTS_ALL_OFF fires -> IDLE
        ambient_harness.assert_state(STATE_IDLE)

    async def test_dark_stays_dark_at_69(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """Start dark (10 lux), increase to 69 -> still dark (below 70)."""
        # Get into dark mode
        await ambient_harness.set_ambient_lux(10)

        await ambient_harness.light_on("light.ceiling", brightness=200)
        ambient_harness.force_state(STATE_AUTO)

        await ambient_harness.set_ambient_lux(69)

        # 69 < 70 (high_threshold), still dark. No change -> stays AUTO.
        ambient_harness.assert_state(STATE_AUTO)

    async def test_hysteresis_prevents_oscillation_near_threshold(
        self, hass: HomeAssistant
    ) -> None:
        """Values near the threshold don't cause rapid dark/bright toggling.

        Once in BRIGHT mode (initial lux=100 > 50), fluctuations between
        31-69 do not cross the low_threshold (30) or high_threshold (70),
        so the darkness state never changes.
        """
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_ambient="100",
        )
        try:
            # Initialize hysteresis (BRIGHT mode) via motion_on
            await h.motion_on()
            h.force_state(STATE_IDLE)

            # Fluctuate around threshold: all values > 30, so stays BRIGHT
            for lux in [55, 45, 60, 35, 50, 31]:
                await h.set_ambient_lux(lux)
                h.assert_state(STATE_IDLE, msg=f"should stay IDLE at {lux} lux")
        finally:
            await h.cleanup()

    async def test_full_bright_dark_bright_cycle(self, hass: HomeAssistant) -> None:
        """Full cycle: bright -> dark(10) -> bright(71) with proper transitions."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_ambient="100",
        )
        try:
            # Initialize hysteresis and set up motion active
            await h.motion_on()
            h.force_state(STATE_IDLE)

            # Drop to 10 -> becomes dark. IDLE + motion -> MOTION_AUTO
            await h.set_ambient_lux(10)
            h.assert_state(STATE_MOTION_AUTO)

            # Simulate lights on, move to AUTO
            await h.light_on("light.ceiling", brightness=200)
            h.force_state(STATE_AUTO)

            spy, called = _make_turn_off_spy(h)
            h.coordinator._async_turn_off_lights = spy

            # Rise to 71 -> becomes bright. AUTO -> turns off -> IDLE
            await h.set_ambient_lux(71)
            await hass.async_block_till_done()

            assert called["value"], "Expected turn_off to be called"
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()


# ===================================================================
# 2. Became Dark With Motion Active
# ===================================================================


class TestBecameDarkWithMotion:
    """When ambient light drops below threshold with motion active."""

    async def test_dark_in_idle_with_motion_fires_motion_on(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """IDLE + motion active + became dark -> MOTION_AUTO."""
        # Turn on motion sensor so trigger reports active.
        # This transitions IDLE -> MOTION_AUTO; force back to IDLE.
        await ambient_harness.motion_on()
        ambient_harness.force_state(STATE_IDLE)

        # Drop lux to trigger dark
        await ambient_harness.set_ambient_lux(29)

        # Ambient handler: is_dark_now=True, motion_active=True, state=IDLE
        # -> fires MOTION_ON -> MOTION_AUTO
        ambient_harness.assert_state(STATE_MOTION_AUTO)

    async def test_dark_in_manual_off_with_motion_stays_manual_off(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """MANUAL_OFF + motion active + became dark -> stays MANUAL_OFF.

        The ambient handler fires MOTION_ON from MANUAL_OFF, but the state
        machine defines MANUAL_OFF + MOTION_ON -> MANUAL_OFF (same state,
        returns False). So state stays MANUAL_OFF.
        """
        await ambient_harness.motion_on()
        ambient_harness.force_state(STATE_MANUAL_OFF)

        await ambient_harness.set_ambient_lux(29)

        ambient_harness.assert_state(STATE_MANUAL_OFF)

    async def test_dark_in_motion_auto_turns_on_lights(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """MOTION_AUTO + became dark -> calls _async_turn_on_lights (re-evaluate brightness)."""
        await ambient_harness.motion_on()
        ambient_harness.force_state(STATE_MOTION_AUTO)

        turn_on_called = False
        original = ambient_harness.coordinator._async_turn_on_lights

        async def spy():
            nonlocal turn_on_called
            turn_on_called = True
            await original()

        ambient_harness.coordinator._async_turn_on_lights = spy

        await ambient_harness.set_ambient_lux(29)

        assert turn_on_called, "Expected _async_turn_on_lights to be called"
        ambient_harness.assert_state(STATE_MOTION_AUTO)

    async def test_dark_in_auto_turns_on_lights(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """AUTO + became dark -> calls _async_turn_on_lights (re-evaluate brightness)."""
        await ambient_harness.light_on("light.ceiling", brightness=200)
        ambient_harness.force_state(STATE_AUTO)

        # Need motion active for the "became dark" branch
        await ambient_harness.motion_on()
        # motion_on from AUTO -> MOTION_AUTO; force back to AUTO
        ambient_harness.force_state(STATE_AUTO)

        turn_on_called = False
        original = ambient_harness.coordinator._async_turn_on_lights

        async def spy():
            nonlocal turn_on_called
            turn_on_called = True
            await original()

        ambient_harness.coordinator._async_turn_on_lights = spy

        await ambient_harness.set_ambient_lux(29)

        assert turn_on_called, "Expected _async_turn_on_lights to be called"
        ambient_harness.assert_state(STATE_AUTO)

    async def test_dark_in_motion_manual_turns_on_lights(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """MOTION_MANUAL + became dark -> calls _async_turn_on_lights."""
        await ambient_harness.motion_on()
        ambient_harness.force_state(STATE_MOTION_MANUAL)

        turn_on_called = False
        original = ambient_harness.coordinator._async_turn_on_lights

        async def spy():
            nonlocal turn_on_called
            turn_on_called = True
            await original()

        ambient_harness.coordinator._async_turn_on_lights = spy

        await ambient_harness.set_ambient_lux(29)

        assert turn_on_called, "Expected _async_turn_on_lights to be called"
        ambient_harness.assert_state(STATE_MOTION_MANUAL)

    async def test_dark_in_manual_turns_on_lights(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """MANUAL + motion active + became dark -> calls _async_turn_on_lights."""
        await ambient_harness.motion_on()
        ambient_harness.force_state(STATE_MANUAL)

        turn_on_called = False
        original = ambient_harness.coordinator._async_turn_on_lights

        async def spy():
            nonlocal turn_on_called
            turn_on_called = True
            await original()

        ambient_harness.coordinator._async_turn_on_lights = spy

        await ambient_harness.set_ambient_lux(29)

        assert turn_on_called, "Expected _async_turn_on_lights to be called"
        ambient_harness.assert_state(STATE_MANUAL)

    async def test_dark_without_motion_no_action(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """IDLE + no motion + became dark -> no state change (motion_active is False)."""
        ambient_harness.force_state(STATE_IDLE)

        # Motion is off (default)
        await ambient_harness.set_ambient_lux(29)

        # No motion active: the "became dark" branch requires motion_active=True
        ambient_harness.assert_state(STATE_IDLE)


# ===================================================================
# 3. Became Bright in Auto States
# ===================================================================


class TestBecameBrightInAutoStates:
    """When ambient light rises above threshold in auto-controlled states."""

    async def test_bright_in_auto_turns_off_lights(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """AUTO + became bright -> turns off lights -> IDLE."""
        # Get into dark mode
        await ambient_harness.set_ambient_lux(10)

        # Set up AUTO with lights on
        await ambient_harness.light_on("light.ceiling", brightness=200)
        ambient_harness.force_state(STATE_AUTO)

        spy, called = _make_turn_off_spy(ambient_harness)
        ambient_harness.coordinator._async_turn_off_lights = spy

        # Increase lux above high_threshold
        await ambient_harness.set_ambient_lux(71)
        # Extra drain: the spy's async_set queues a light state_changed event
        # that may not be processed within set_ambient_lux's async_block_till_done.
        await hass.async_block_till_done()

        assert called["value"], "Expected _async_turn_off_lights to be called"
        # The light state change handler fires LIGHTS_ALL_OFF -> IDLE
        ambient_harness.assert_state(STATE_IDLE)

    async def test_bright_in_motion_auto_turns_off_lights(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """MOTION_AUTO + became bright -> turns off lights -> IDLE."""
        # Get into dark mode
        await ambient_harness.set_ambient_lux(10)

        await ambient_harness.motion_on()
        await ambient_harness.light_on("light.ceiling", brightness=200)
        ambient_harness.force_state(STATE_MOTION_AUTO)

        spy, called = _make_turn_off_spy(ambient_harness)
        ambient_harness.coordinator._async_turn_off_lights = spy

        await ambient_harness.set_ambient_lux(71)
        await hass.async_block_till_done()

        assert called["value"], "Expected _async_turn_off_lights to be called"
        ambient_harness.assert_state(STATE_IDLE)

    async def test_bright_in_auto_cancels_timers(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """AUTO + became bright -> cancels all timers."""
        # Get into dark mode
        await ambient_harness.set_ambient_lux(10)

        await ambient_harness.light_on("light.ceiling", brightness=200)
        ambient_harness.force_state(STATE_AUTO)

        # Increase to bright
        await ambient_harness.set_ambient_lux(71)

        ambient_harness.assert_no_active_timers()


# ===================================================================
# 4. Became Bright in Manual States
# ===================================================================


class TestBecameBrightInManualStates:
    """When ambient light rises in manually-controlled states, user retains control."""

    async def test_bright_in_manual_does_not_turn_off(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """MANUAL + became bright -> stays MANUAL (user has control)."""
        # Get into dark mode
        await ambient_harness.set_ambient_lux(10)

        await ambient_harness.light_on("light.ceiling", brightness=200)
        ambient_harness.force_state(STATE_MANUAL)

        turn_off_called = False

        async def spy():
            nonlocal turn_off_called
            turn_off_called = True

        ambient_harness.coordinator._async_turn_off_lights = spy

        await ambient_harness.set_ambient_lux(71)

        assert not turn_off_called, "Should NOT call _async_turn_off_lights in MANUAL"
        ambient_harness.assert_state(STATE_MANUAL)

    async def test_bright_in_motion_manual_does_not_turn_off(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """MOTION_MANUAL + became bright -> stays MOTION_MANUAL (user has control)."""
        # Get into dark mode
        await ambient_harness.set_ambient_lux(10)

        await ambient_harness.motion_on()
        await ambient_harness.light_on("light.ceiling", brightness=200)
        ambient_harness.force_state(STATE_MOTION_MANUAL)

        turn_off_called = False

        async def spy():
            nonlocal turn_off_called
            turn_off_called = True

        ambient_harness.coordinator._async_turn_off_lights = spy

        await ambient_harness.set_ambient_lux(71)

        assert not turn_off_called, (
            "Should NOT call _async_turn_off_lights in MOTION_MANUAL"
        )
        ambient_harness.assert_state(STATE_MOTION_MANUAL)

    async def test_bright_in_overridden_does_not_turn_off(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """OVERRIDDEN + became bright -> stays OVERRIDDEN (automation disabled)."""
        # Get into dark mode
        await ambient_harness.set_ambient_lux(10)

        ambient_harness.force_state(STATE_OVERRIDDEN)

        await ambient_harness.set_ambient_lux(71)

        # OVERRIDDEN is not in the handled states for became-bright
        ambient_harness.assert_state(STATE_OVERRIDDEN)


# ===================================================================
# 5. No Ambient Sensor Configured
# ===================================================================


class TestNoAmbientSensor:
    """Without an ambient sensor, lights always come on with motion (no gating)."""

    async def test_no_ambient_sensor_treats_as_dark(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """No ambient sensor configured -> motion always activates lights."""
        harness.assert_state(STATE_IDLE)

        await harness.motion_on()

        # Should transition to MOTION_AUTO regardless of ambient light
        harness.assert_state(STATE_MOTION_AUTO)

    async def test_no_ambient_sensor_motion_cycle_works(
        self, hass: HomeAssistant, harness: CoordinatorHarness
    ) -> None:
        """Full motion cycle works without ambient sensor."""
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)

        await harness.motion_off()
        harness.assert_state(STATE_AUTO)
        harness.assert_timer_active("motion")


# ===================================================================
# 6. Ambient With Motion Activation Disabled
# ===================================================================


class TestAmbientWithMotionActivationDisabled:
    """Ambient sensor with motion_activation=False."""

    async def test_dark_idle_motion_on_no_activation(self, hass: HomeAssistant) -> None:
        """motion_activation=False: dark + motion active in IDLE -> no transition."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
                CONF_MOTION_ACTIVATION: False,
            },
            initial_ambient="100",
        )
        try:
            h.assert_state(STATE_IDLE)

            # Turn on motion
            await h.motion_on()
            # motion_activation=False: motion handler doesn't fire MOTION_ON
            h.assert_state(STATE_IDLE)

            # Drop lux to become dark
            await h.set_ambient_lux(29)

            # Ambient handler checks self.motion_activation which is False
            # -> the "became dark + motion + motion_activation" branch is skipped
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_dark_auto_no_motion_activation_no_turn_on(
        self, hass: HomeAssistant
    ) -> None:
        """motion_activation=False: dark + AUTO state -> no light turn-on from ambient."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
                CONF_MOTION_ACTIVATION: False,
            },
            initial_ambient="100",
        )
        try:
            # Set motion on (won't transition since motion_activation=False)
            await h.motion_on()
            h.force_state(STATE_AUTO)

            turn_on_called = False
            original = h.coordinator._async_turn_on_lights

            async def spy():
                nonlocal turn_on_called
                turn_on_called = True
                await original()

            h.coordinator._async_turn_on_lights = spy

            await h.set_ambient_lux(29)

            # The "became dark" branch requires motion_activation=True
            assert not turn_on_called, (
                "Should NOT turn on lights when motion_activation is disabled"
            )
        finally:
            await h.cleanup()


# ===================================================================
# 7. Binary Ambient Sensor
# ===================================================================


class TestBinaryAmbientSensor:
    """Binary sensor as ambient light input (no lux unit, on/off = dark/bright)."""

    async def test_binary_sensor_on_means_dark(self, hass: HomeAssistant) -> None:
        """binary_sensor 'on' = dark inside -> motion triggers lights."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_AMBIENT_LIGHT_SENSOR: "binary_sensor.dark",
            },
        )
        try:
            # Set binary sensor to "off" (bright) without lux unit
            hass.states.async_set("binary_sensor.dark", "off")
            await hass.async_block_till_done()

            h.assert_state(STATE_IDLE)

            # Turn on motion. Since binary_sensor is "off" (bright), the
            # brightness strategy returns 0 but state still transitions to MOTION_AUTO.
            await h.motion_on()
            h.force_state(STATE_IDLE)

            # Now make it dark
            hass.states.async_set("binary_sensor.dark", "on")
            await hass.async_block_till_done()

            # binary_sensor "on" = dark. IDLE + motion active + dark -> MOTION_AUTO
            h.assert_state(STATE_MOTION_AUTO)
        finally:
            await h.cleanup()

    async def test_binary_sensor_off_means_bright(self, hass: HomeAssistant) -> None:
        """binary_sensor 'off' = bright inside -> became bright turns off auto lights."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_AMBIENT_LIGHT_SENSOR: "binary_sensor.dark",
            },
        )
        try:
            # Start with "on" (dark)
            hass.states.async_set("binary_sensor.dark", "on")
            await hass.async_block_till_done()

            # Set up AUTO with lights on
            await h.light_on("light.ceiling", brightness=200)
            h.force_state(STATE_AUTO)

            # Spy on turn_off and simulate lights going off with integration context
            spy, called = _make_turn_off_spy(h)
            h.coordinator._async_turn_off_lights = spy

            # Switch to "off" (bright)
            hass.states.async_set("binary_sensor.dark", "off")
            await hass.async_block_till_done()
            await hass.async_block_till_done()

            assert called["value"], "Expected _async_turn_off_lights to be called"
            # Became bright in AUTO -> turns off lights -> IDLE
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_binary_sensor_no_change_no_action(self, hass: HomeAssistant) -> None:
        """binary_sensor stays 'off' (bright) -> no action."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_AMBIENT_LIGHT_SENSOR: "binary_sensor.dark",
            },
        )
        try:
            hass.states.async_set("binary_sensor.dark", "off")
            await hass.async_block_till_done()

            h.force_state(STATE_AUTO)

            # Set again to "off" -> no change in darkness state
            hass.states.async_set("binary_sensor.dark", "off")
            await hass.async_block_till_done()

            # No action, stays AUTO
            h.assert_state(STATE_AUTO)
        finally:
            await h.cleanup()


# ===================================================================
# 8. Edge Cases
# ===================================================================


class TestAmbientEdgeCases:
    """Edge cases for ambient light handling."""

    async def test_exact_low_threshold_triggers_dark(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """Lux exactly at low_threshold (30) triggers dark (uses <=)."""
        # Initialize hysteresis and set up motion active
        await ambient_harness.motion_on()
        ambient_harness.force_state(STATE_IDLE)

        await ambient_harness.set_ambient_lux(30)

        # 30 <= 30 -> switches to DIM. IDLE + motion active + dark -> MOTION_AUTO
        ambient_harness.assert_state(STATE_MOTION_AUTO)

    async def test_exact_high_threshold_triggers_bright(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """Lux exactly at high_threshold (70) triggers bright (uses >=)."""
        # Get into dark mode
        await ambient_harness.set_ambient_lux(10)

        await ambient_harness.light_on("light.ceiling", brightness=200)
        ambient_harness.force_state(STATE_AUTO)

        spy, called = _make_turn_off_spy(ambient_harness)
        ambient_harness.coordinator._async_turn_off_lights = spy

        await ambient_harness.set_ambient_lux(70)
        await hass.async_block_till_done()

        # 70 >= 70 -> switches to BRIGHT. AUTO + bright -> turns off -> IDLE
        assert called["value"]
        ambient_harness.assert_state(STATE_IDLE)

    async def test_ambient_change_during_overridden_no_effect(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """Ambient changes while OVERRIDDEN have no effect on state."""
        ambient_harness.force_state(STATE_OVERRIDDEN)

        await ambient_harness.set_ambient_lux(10)
        ambient_harness.assert_state(STATE_OVERRIDDEN)

        await ambient_harness.set_ambient_lux(100)
        ambient_harness.assert_state(STATE_OVERRIDDEN)

    async def test_ambient_change_in_manual_off_without_motion(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """MANUAL_OFF + no motion + became dark -> no transition."""
        ambient_harness.force_state(STATE_MANUAL_OFF)

        # Motion is off -> motion_active=False
        await ambient_harness.set_ambient_lux(29)

        # The "became dark" branch requires motion_active=True
        ambient_harness.assert_state(STATE_MANUAL_OFF)

    async def test_rapid_lux_changes_respect_hysteresis(
        self, hass: HomeAssistant, ambient_harness: CoordinatorHarness
    ) -> None:
        """Rapid lux fluctuations within hysteresis band don't cause state changes."""
        ambient_harness.force_state(STATE_IDLE)

        # Fluctuate within bright range: 100 -> 50 -> 40 -> 35 -> 31
        for lux in [50, 40, 35, 31]:
            await ambient_harness.set_ambient_lux(lux)
            ambient_harness.assert_state(
                STATE_IDLE, msg=f"should stay IDLE at {lux} lux"
            )

    async def test_first_evaluation_initializes_dark_mode(
        self, hass: HomeAssistant
    ) -> None:
        """First lux evaluation below threshold initializes as dark."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_ambient="20",  # Start below threshold -> dark
        )
        try:
            h.assert_state(STATE_IDLE)

            # Motion should trigger lights since ambient is dark
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
        finally:
            await h.cleanup()

    async def test_first_evaluation_initializes_bright_mode(
        self, hass: HomeAssistant
    ) -> None:
        """First lux evaluation above threshold initializes as bright."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_ambient="80",  # Start above threshold -> bright
        )
        try:
            h.assert_state(STATE_IDLE)

            # Motion triggers MOTION_AUTO state transition, but brightness
            # strategy returns 0 because is_dark_inside=False
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            # Verify context reports bright
            context = h.coordinator._get_context()
            assert context["is_dark_inside"] is False
        finally:
            await h.cleanup()
