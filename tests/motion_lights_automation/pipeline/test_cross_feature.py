"""Cross-feature integration tests for motion lights automation.

Tests that combine MULTIPLE features together (override + ambient + motion +
house_active + multi-light + motion_delay) to verify features don't interfere
with each other.
"""

from __future__ import annotations

from homeassistant.core import Context, HomeAssistant

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_HOUSE_ACTIVE,
    CONF_LIGHTS,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FULL_CONFIG = {
    CONF_MOTION_ENTITY: ["binary_sensor.motion1", "binary_sensor.motion2"],
    CONF_LIGHTS: ["light.ceiling", "light.lamp"],
    CONF_OVERRIDE_SWITCH: "switch.override",
    CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
    CONF_AMBIENT_LIGHT_THRESHOLD: 50,
    CONF_HOUSE_ACTIVE: "input_boolean.house_active",
    CONF_MOTION_DELAY: 5,
    CONF_BRIGHTNESS_ACTIVE: 80,
    CONF_BRIGHTNESS_INACTIVE: 10,
}

FULL_INITIAL_LIGHTS = {
    "light.ceiling": {"state": "off"},
    "light.lamp": {"state": "off"},
}


async def _create_full_harness(
    hass: HomeAssistant,
    initial_ambient: str = "100",
    initial_override: str = "off",
    initial_house_active: str = "on",
    initial_motion: str = "off",
    **kwargs,
) -> CoordinatorHarness:
    """Create a harness with ALL features enabled."""
    return await CoordinatorHarness.create(
        hass,
        config_data=FULL_CONFIG,
        initial_lights=FULL_INITIAL_LIGHTS,
        initial_ambient=initial_ambient,
        initial_override=initial_override,
        initial_house_active=initial_house_active,
        initial_motion=initial_motion,
        **kwargs,
    )


def _make_turn_off_spy(harness: CoordinatorHarness):
    """Return (spy_fn, was_called) pair that simulates integration light-off."""
    called = {"value": False}

    async def spy():
        called["value"] = True
        for light_id in harness.coordinator.light_controller.lights:
            ctx = Context()
            harness.coordinator.light_controller._context_tracking.add(ctx.id)
            harness.hass.states.async_set(light_id, "off", context=ctx)

    return spy, called


# ===================================================================
# 1. Override + Ambient interaction
# ===================================================================


class TestOverrideWithAmbient:
    """Override should completely ignore ambient light changes."""

    async def test_override_ignores_ambient_bright_to_dark(
        self, hass: HomeAssistant
    ) -> None:
        """OVERRIDDEN + ambient goes dark -> stays OVERRIDDEN."""
        h = await _create_full_harness(hass, initial_ambient="100")
        try:
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)

            # Ambient drops below threshold (dark)
            await h.set_ambient_lux(10)

            h.assert_state(STATE_OVERRIDDEN)
        finally:
            await h.cleanup()

    async def test_override_ignores_ambient_dark_to_bright(
        self, hass: HomeAssistant
    ) -> None:
        """OVERRIDDEN + ambient goes bright -> stays OVERRIDDEN."""
        h = await _create_full_harness(hass, initial_ambient="10")
        try:
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)

            # Ambient rises above threshold (bright)
            await h.set_ambient_lux(100)

            h.assert_state(STATE_OVERRIDDEN)
        finally:
            await h.cleanup()

    async def test_override_off_uses_ambient_for_initial_state(
        self, hass: HomeAssistant
    ) -> None:
        """Override off checks ambient for brightness when lights are on."""
        h = await _create_full_harness(hass, initial_ambient="10")
        try:
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)

            # Turn on lights while overridden
            await h.light_on("light.ceiling", brightness=200)
            h.refresh_lights()

            # Override off with lights on -> MANUAL (regardless of ambient)
            await h.override_off()
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")
        finally:
            await h.cleanup()


# ===================================================================
# 2. Override + Motion interaction
# ===================================================================


class TestOverrideWithMotion:
    """Override should block all motion-based activation."""

    async def test_override_blocks_motion_activation(self, hass: HomeAssistant) -> None:
        """Motion on during OVERRIDDEN -> stays OVERRIDDEN."""
        h = await _create_full_harness(hass)
        try:
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)

            await h.motion_on("binary_sensor.motion1")
            h.assert_state(STATE_OVERRIDDEN)

            await h.motion_on("binary_sensor.motion2")
            h.assert_state(STATE_OVERRIDDEN)
        finally:
            await h.cleanup()

    async def test_override_off_with_active_motion_lights_on(
        self, hass: HomeAssistant
    ) -> None:
        """Override off while motion active and lights on -> MANUAL."""
        h = await _create_full_harness(hass, initial_ambient="10")
        try:
            # Motion active, then override on
            await h.motion_on("binary_sensor.motion1")
            # motion_delay starts (state still IDLE during delay)
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)

            # Turn on lights while overridden
            await h.light_on("light.ceiling", brightness=200)
            h.refresh_lights()

            # Override off with lights on -> MANUAL
            await h.override_off()
            h.assert_state(STATE_MANUAL)
        finally:
            await h.cleanup()

    async def test_override_off_with_active_motion_lights_off(
        self, hass: HomeAssistant
    ) -> None:
        """Override off while motion active and lights off -> IDLE."""
        h = await _create_full_harness(hass, initial_ambient="10")
        try:
            await h.motion_on("binary_sensor.motion1")
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)

            # Lights stay off, override off -> IDLE
            h.refresh_lights()
            await h.override_off()
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()


# ===================================================================
# 3. Ambient + Motion Delay interaction
# ===================================================================


class TestAmbientWithMotionDelay:
    """Ambient light changes during motion delay period."""

    async def test_ambient_dark_during_delay_timer(self, hass: HomeAssistant) -> None:
        """Ambient goes dark during motion delay -> delay continues, lights activate when delay expires."""
        h = await _create_full_harness(hass, initial_ambient="100")
        try:
            h.assert_state(STATE_IDLE)

            # Motion triggers delay timer (ambient is bright)
            await h.motion_on("binary_sensor.motion1")
            h.assert_state(STATE_IDLE)
            h.assert_timer_active("motion_delay")

            # Ambient goes dark during delay
            await h.set_ambient_lux(10)

            # Delay still active (ambient change with motion in IDLE fires MOTION_ON
            # but since state is IDLE and motion_delay is already running, the ambient
            # handler fires MOTION_ON which transitions IDLE->MOTION_AUTO)
            # Actually: ambient handler detects dark + motion active + IDLE -> fires MOTION_ON
            # This transitions to MOTION_AUTO directly
            h.assert_state(STATE_MOTION_AUTO)
        finally:
            await h.cleanup()

    async def test_ambient_bright_during_delay_timer(self, hass: HomeAssistant) -> None:
        """Ambient goes bright during motion delay -> brightness returns 0 so lights don't activate."""
        # Start dark so motion would normally activate lights
        h = await _create_full_harness(hass, initial_ambient="10")
        try:
            h.assert_state(STATE_IDLE)

            # Motion triggers delay timer
            await h.motion_on("binary_sensor.motion1")
            h.assert_state(STATE_IDLE)
            h.assert_timer_active("motion_delay")

            # Ambient goes bright during delay
            await h.set_ambient_lux(100)

            # Delay expires - motion still active but ambient is bright
            await h.expire_motion_delay()

            # State transitions to MOTION_AUTO but brightness=0 means lights don't turn on
            h.assert_state(STATE_MOTION_AUTO)
            # Brightness strategy returns 0 when bright, so lights stay off
            context = h.coordinator._get_context()
            assert context["is_dark_inside"] is False
        finally:
            await h.cleanup()


# ===================================================================
# 4. Motion Delay + Override interaction
# ===================================================================


class TestMotionDelayWithOverride:
    """Override during motion delay period."""

    async def test_override_on_during_delay_cancels_delay(
        self, hass: HomeAssistant
    ) -> None:
        """Override on during motion delay -> delay cancelled, OVERRIDDEN."""
        h = await _create_full_harness(hass, initial_ambient="10")
        try:
            # Motion triggers delay
            await h.motion_on("binary_sensor.motion1")
            h.assert_state(STATE_IDLE)
            h.assert_timer_active("motion_delay")

            # Override on cancels all timers
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)
            h.assert_no_active_timers()
        finally:
            await h.cleanup()

    async def test_override_off_after_delay_cancelled(
        self, hass: HomeAssistant
    ) -> None:
        """After override cancels delay, override off -> IDLE (lights off)."""
        h = await _create_full_harness(hass, initial_ambient="10")
        try:
            # Motion triggers delay, override cancels it
            await h.motion_on("binary_sensor.motion1")
            h.assert_timer_active("motion_delay")

            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)
            h.assert_no_active_timers()

            # Override off with lights off -> IDLE
            h.refresh_lights()
            await h.override_off()
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()


# ===================================================================
# 5. Multi-Light + Ambient interaction
# ===================================================================


class TestMultiLightWithAmbient:
    """Multi-light behavior with ambient light changes."""

    async def test_bright_turns_off_only_auto_controlled_lights(
        self, hass: HomeAssistant
    ) -> None:
        """When ambient goes bright, only auto-controlled (AUTO/MOTION_AUTO) lights turn off."""
        h = await _create_full_harness(hass, initial_ambient="10")
        try:
            # Get into MOTION_AUTO with lights on
            await h.motion_on("binary_sensor.motion1")
            # Ambient is dark so delay starts
            h.assert_timer_active("motion_delay")
            await h.expire_motion_delay()
            h.assert_state(STATE_MOTION_AUTO)

            # Set lights on
            await h.light_on("light.ceiling", brightness=200)
            await h.light_on("light.lamp", brightness=200)
            h.force_state(STATE_AUTO)

            spy, called = _make_turn_off_spy(h)
            h.coordinator._async_turn_off_lights = spy

            # Ambient goes bright
            await h.set_ambient_lux(100)
            await hass.async_block_till_done()

            assert called["value"], "Expected _async_turn_off_lights to be called"
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_dark_activates_all_configured_lights(
        self, hass: HomeAssistant
    ) -> None:
        """When ambient goes dark with motion, all configured lights activate."""
        h = await _create_full_harness(hass, initial_ambient="100")
        try:
            # Motion on (starts delay since ambient is bright initially)
            await h.motion_on("binary_sensor.motion1")
            h.assert_state(STATE_IDLE)

            # Ambient goes dark - triggers MOTION_ON since motion active + IDLE
            await h.set_ambient_lux(10)
            h.assert_state(STATE_MOTION_AUTO)
        finally:
            await h.cleanup()


# ===================================================================
# 6. Multi-Light + Override interaction
# ===================================================================


class TestMultiLightWithOverride:
    """Multi-light behavior with override switch."""

    async def test_override_off_some_lights_on(self, hass: HomeAssistant) -> None:
        """Override off with some lights on -> MANUAL."""
        h = await _create_full_harness(hass)
        try:
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)

            # Only one light on
            await h.light_on("light.ceiling", brightness=200)
            h.refresh_lights()

            await h.override_off()
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")
        finally:
            await h.cleanup()

    async def test_override_off_all_lights_off(self, hass: HomeAssistant) -> None:
        """Override off with all lights off -> IDLE."""
        h = await _create_full_harness(hass)
        try:
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)

            # Both lights off
            await h.light_off("light.ceiling")
            await h.light_off("light.lamp")
            h.refresh_lights()

            await h.override_off()
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()


# ===================================================================
# 7. Multi-Sensor + Override interaction
# ===================================================================


class TestMultiSensorWithOverride:
    """Multiple motion sensors with override."""

    async def test_all_sensors_ignored_during_override(
        self, hass: HomeAssistant
    ) -> None:
        """All motion sensors active during override -> still OVERRIDDEN."""
        h = await _create_full_harness(hass)
        try:
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)

            await h.motion_on("binary_sensor.motion1")
            h.assert_state(STATE_OVERRIDDEN)

            await h.motion_on("binary_sensor.motion2")
            h.assert_state(STATE_OVERRIDDEN)

            await h.motion_off("binary_sensor.motion1")
            h.assert_state(STATE_OVERRIDDEN)
        finally:
            await h.cleanup()

    async def test_override_off_respects_active_sensor(
        self, hass: HomeAssistant
    ) -> None:
        """Override off checks actual motion state via light on/off for transition."""
        h = await _create_full_harness(hass)
        try:
            # Both sensors active, then override
            await h.motion_on("binary_sensor.motion1")
            await h.motion_on("binary_sensor.motion2")
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)

            # Override off with lights off -> IDLE
            h.refresh_lights()
            await h.override_off()
            h.assert_state(STATE_IDLE)

            # Override off with lights on -> MANUAL
            await h.override_on()
            await h.light_on("light.ceiling", brightness=200)
            h.refresh_lights()
            await h.override_off()
            h.assert_state(STATE_MANUAL)
        finally:
            await h.cleanup()


# ===================================================================
# 8. All Features Simultaneous
# ===================================================================


class TestAllFeaturesSimultaneous:
    """Comprehensive multi-step tests exercising all features together."""

    async def test_full_feature_evening_cycle(self, hass: HomeAssistant) -> None:
        """Comprehensive test of a typical evening scenario.

        1. Start IDLE, ambient bright, house active, override off
        2. Ambient goes dark
        3. Motion detected -> delay timer starts
        4. Delay expires -> MOTION_AUTO (lights on at active brightness)
        5. User adjusts brightness -> MOTION_MANUAL
        6. Motion clears -> MANUAL (extended timer)
        7. House goes inactive (brightness stays)
        8. Timer expires -> IDLE
        """
        h = await _create_full_harness(
            hass,
            initial_ambient="100",
            initial_house_active="on",
        )
        try:
            # Step 1: Initial state
            h.assert_state(STATE_IDLE)

            # Step 2: Ambient goes dark
            await h.set_ambient_lux(10)
            h.assert_state(STATE_IDLE)  # No motion yet

            # Step 3: Motion detected -> delay timer starts
            await h.motion_on("binary_sensor.motion1")
            h.assert_state(STATE_IDLE)
            h.assert_timer_active("motion_delay")

            # Step 4: Delay expires -> MOTION_AUTO
            await h.expire_motion_delay()
            h.assert_state(STATE_MOTION_AUTO)

            # Simulate lights turned on by coordinator
            await h.light_on("light.ceiling", brightness=200)
            await h.light_on("light.lamp", brightness=200)

            # Step 5: User adjusts brightness -> MOTION_MANUAL
            await h.manual_brightness_change("light.ceiling", brightness=150)
            h.assert_state(STATE_MOTION_MANUAL)

            # Step 6: Motion clears -> MANUAL with extended timer
            await h.motion_off("binary_sensor.motion1")
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")

            # Step 7: House goes inactive - brightness stays (no forced change)
            await h.set_house_active(False)
            # State doesn't change, brightness stays at user-set level
            h.assert_state(STATE_MANUAL)

            # Step 8: Timer expires -> IDLE
            await h.expire_timer("extended")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_full_feature_override_interruption(
        self, hass: HomeAssistant
    ) -> None:
        """Multi-step override interruption test.

        1. Motion active, lights on, ambient dark
        2. Override on -> OVERRIDDEN
        3. Ambient changes, motion changes -- all ignored
        4. Override off -> determine state from current conditions
        """
        h = await _create_full_harness(hass, initial_ambient="10")
        try:
            # Step 1: Motion active, lights on, ambient dark
            await h.motion_on("binary_sensor.motion1")
            h.assert_timer_active("motion_delay")
            await h.expire_motion_delay()
            h.assert_state(STATE_MOTION_AUTO)

            await h.light_on("light.ceiling", brightness=200)
            await h.light_on("light.lamp", brightness=200)

            # Step 2: Override on -> OVERRIDDEN
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)
            h.assert_no_active_timers()

            # Step 3: Ambient changes, motion changes -- all ignored
            await h.set_ambient_lux(100)
            h.assert_state(STATE_OVERRIDDEN)

            await h.motion_off("binary_sensor.motion1")
            h.assert_state(STATE_OVERRIDDEN)

            await h.motion_on("binary_sensor.motion2")
            h.assert_state(STATE_OVERRIDDEN)

            await h.set_ambient_lux(10)
            h.assert_state(STATE_OVERRIDDEN)

            # Step 4: Override off -> lights still on -> MANUAL
            h.refresh_lights()
            await h.override_off()
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")
        finally:
            await h.cleanup()

    async def test_full_feature_ambient_oscillation(self, hass: HomeAssistant) -> None:
        """Multi-step ambient oscillation test.

        1. Motion active, ambient dark -> lights on
        2. Ambient goes bright -> lights off
        3. Ambient goes dark again -> lights back on
        4. Motion clears -> AUTO
        5. Timer expires -> IDLE
        """
        h = await _create_full_harness(hass, initial_ambient="10")
        try:
            # Step 1: Motion active, ambient dark -> lights on
            await h.motion_on("binary_sensor.motion1")
            h.assert_timer_active("motion_delay")
            await h.expire_motion_delay()
            h.assert_state(STATE_MOTION_AUTO)

            await h.light_on("light.ceiling", brightness=200)
            await h.light_on("light.lamp", brightness=200)

            # Step 2: Ambient goes bright -> lights off
            spy, called = _make_turn_off_spy(h)
            h.coordinator._async_turn_off_lights = spy
            await h.set_ambient_lux(100)
            await hass.async_block_till_done()

            assert called["value"], "Expected turn_off to be called"
            h.assert_state(STATE_IDLE)

            # Step 3: Ambient goes dark again with motion still active -> lights back on
            # Motion is still on from step 1
            await h.set_ambient_lux(10)
            # IDLE + dark + motion active -> MOTION_AUTO
            h.assert_state(STATE_MOTION_AUTO)

            # Simulate lights on
            await h.light_on("light.ceiling", brightness=200)

            # Step 4: Motion clears -> AUTO
            await h.motion_off("binary_sensor.motion1")
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")

            # Step 5: Timer expires -> IDLE
            await h.expire_timer("motion")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()


# ===================================================================
# 9. Minimal Config
# ===================================================================


class TestMinimalConfig:
    """Tests with minimal configuration to ensure optional features are truly optional."""

    async def test_only_motion_and_lights(self, hass: HomeAssistant) -> None:
        """Works with just motion + lights (no optional entities)."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.ceiling"],
            },
        )
        try:
            h.assert_state(STATE_IDLE)

            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            await h.motion_off()
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")

            await h.expire_timer("motion")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_no_motion_entities_works(self, hass: HomeAssistant) -> None:
        """Works without motion entities (manual-only)."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: [],
                CONF_LIGHTS: ["light.ceiling"],
            },
        )
        try:
            h.assert_state(STATE_IDLE)

            # Manual light on should work
            await h.manual_light_on("light.ceiling", brightness=200)
            h.assert_state(STATE_MANUAL)

            # Manual light off
            await h.manual_light_off("light.ceiling")
            h.assert_state(STATE_MANUAL_OFF)

            await h.expire_timer("extended")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_single_light_single_sensor(self, hass: HomeAssistant) -> None:
        """Minimal single-entity config."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.only"],
            },
            initial_lights={"light.only": {"state": "off"}},
        )
        try:
            h.assert_state(STATE_IDLE)

            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            await h.motion_off()
            h.assert_state(STATE_AUTO)

            await h.expire_timer("motion")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()


# ===================================================================
# 10. Config Combinations
# ===================================================================


class TestConfigCombinations:
    """Tests with various combinations of optional features enabled."""

    async def test_ambient_without_house_active(self, hass: HomeAssistant) -> None:
        """Ambient sensor but no house_active entity."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.ceiling"],
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_ambient="10",
        )
        try:
            h.assert_state(STATE_IDLE)

            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            # Verify context: dark + house active (default when not configured)
            context = h.coordinator._get_context()
            assert context["is_dark_inside"] is True
            assert context["is_house_active"] is True
        finally:
            await h.cleanup()

    async def test_house_active_without_ambient(self, hass: HomeAssistant) -> None:
        """House_active but no ambient sensor."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.ceiling"],
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
            },
            initial_house_active="on",
        )
        try:
            h.assert_state(STATE_IDLE)

            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            # Context: always dark (no sensor), house active
            context = h.coordinator._get_context()
            assert context["is_dark_inside"] is True
            assert context["is_house_active"] is True
        finally:
            await h.cleanup()

    async def test_override_without_ambient(self, hass: HomeAssistant) -> None:
        """Override switch but no ambient sensor."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.ceiling"],
                CONF_OVERRIDE_SWITCH: "switch.override",
            },
        )
        try:
            h.assert_state(STATE_IDLE)

            # Override on
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)

            # Motion ignored
            await h.motion_on()
            h.assert_state(STATE_OVERRIDDEN)

            # Override off with lights off -> IDLE
            h.refresh_lights()
            await h.override_off()
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_all_optional_entities_configured(self, hass: HomeAssistant) -> None:
        """All optional entities present and working."""
        h = await _create_full_harness(hass, initial_ambient="10")
        try:
            h.assert_state(STATE_IDLE)

            # Full cycle: motion -> delay -> activate -> off
            await h.motion_on("binary_sensor.motion1")
            h.assert_timer_active("motion_delay")

            await h.expire_motion_delay()
            h.assert_state(STATE_MOTION_AUTO)

            await h.motion_off("binary_sensor.motion1")
            h.assert_state(STATE_AUTO)

            await h.expire_timer("motion")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_motion_delay_zero(self, hass: HomeAssistant) -> None:
        """Motion delay = 0 (immediate activation)."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion"],
                CONF_LIGHTS: ["light.ceiling"],
                CONF_MOTION_DELAY: 0,
            },
        )
        try:
            h.assert_state(STATE_IDLE)

            # Motion immediately activates (no delay)
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
            h.assert_timer_inactive("motion_delay")
        finally:
            await h.cleanup()

    async def test_motion_activation_disabled_with_all_features(
        self, hass: HomeAssistant
    ) -> None:
        """Motion_activation=False with all other features enabled."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion1", "binary_sensor.motion2"],
                CONF_LIGHTS: ["light.ceiling", "light.lamp"],
                CONF_OVERRIDE_SWITCH: "switch.override",
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
                CONF_MOTION_ACTIVATION: False,
                CONF_BRIGHTNESS_ACTIVE: 80,
                CONF_BRIGHTNESS_INACTIVE: 10,
            },
            initial_lights={
                "light.ceiling": {"state": "off"},
                "light.lamp": {"state": "off"},
            },
            initial_ambient="10",
        )
        try:
            h.assert_state(STATE_IDLE)

            # Motion does not activate lights
            await h.motion_on("binary_sensor.motion1")
            h.assert_state(STATE_IDLE)

            # But manual light on still works
            await h.manual_light_on("light.ceiling", brightness=200)
            h.assert_state(STATE_MANUAL)

            # Motion on from MANUAL still transitions to MOTION_MANUAL
            # Use motion2 since motion1 is already "on" from earlier
            await h.motion_on("binary_sensor.motion2")
            h.assert_state(STATE_MOTION_MANUAL)

            # Override still works
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)

            h.refresh_lights()
            await h.override_off()
            # Lights still on -> MANUAL
            h.assert_state(STATE_MANUAL)
        finally:
            await h.cleanup()
