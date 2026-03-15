"""Pipeline tests for house active feature across all states.

Tests the full coordinator pipeline when the house active entity changes,
verifying brightness adjustments, state preservation, and interaction with
motion, ambient light, and manual states.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_HOUSE_ACTIVE,
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


async def _create_house_harness(
    hass: HomeAssistant,
    initial_house_active: str = "on",
    **extra_config,
) -> CoordinatorHarness:
    """Create a harness with house_active configured."""
    config = {
        CONF_HOUSE_ACTIVE: "input_boolean.house_active",
    }
    config.update(extra_config)
    return await CoordinatorHarness.create(
        hass,
        config_data=config,
        initial_house_active=initial_house_active,
    )


def _make_turn_on_spy(harness: CoordinatorHarness):
    """Return (spy_fn, called_dict) that wraps _async_turn_on_lights.

    The spy delegates to the original method so side-effects still happen,
    but records whether it was called.
    """
    called = {"value": False}
    original = harness.coordinator._async_turn_on_lights

    async def spy():
        called["value"] = True
        await original()

    return spy, called


# ===================================================================
# 1. House Active Changes In Each State
# ===================================================================


class TestHouseActiveChangesInEachState:
    """Test house active/inactive transitions in every state machine state.

    The coordinator only adjusts brightness in states where lights are
    auto-controlled (AUTO, MOTION_AUTO, MOTION_MANUAL, MANUAL) and only
    when lights are actually on. Going inactive keeps current brightness;
    going active re-applies brightness via _async_turn_on_lights.
    """

    async def test_house_inactive_in_idle_no_effect(self, hass: HomeAssistant) -> None:
        """IDLE with no lights on -- house going inactive has no effect."""
        h = await _create_house_harness(hass, initial_house_active="on")
        try:
            h.assert_state(STATE_IDLE)

            await h.set_house_active(False)

            h.assert_state(STATE_IDLE)
            context = h.coordinator._get_context()
            assert context["is_house_active"] is False
        finally:
            await h.cleanup()

    async def test_house_inactive_in_motion_auto_keeps_current_brightness(
        self, hass: HomeAssistant
    ) -> None:
        """MOTION_AUTO + house goes inactive -- brightness is NOT reduced."""
        h = await _create_house_harness(hass, initial_house_active="on")
        try:
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
            await h.light_on("light.ceiling", brightness=204)  # ~80%

            spy, called = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy

            await h.set_house_active(False)

            h.assert_state(STATE_MOTION_AUTO)
            assert not called["value"], (
                "_async_turn_on_lights should NOT be called when house goes inactive"
            )
            context = h.coordinator._get_context()
            assert context["is_house_active"] is False
        finally:
            await h.cleanup()

    async def test_house_active_in_motion_auto_adjusts_brightness(
        self, hass: HomeAssistant
    ) -> None:
        """MOTION_AUTO + house goes active -- brightness re-applied."""
        h = await _create_house_harness(hass, initial_house_active="off")
        try:
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
            await h.light_on("light.ceiling", brightness=26)  # ~10%

            spy, called = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy

            await h.set_house_active(True)

            h.assert_state(STATE_MOTION_AUTO)
            assert called["value"], (
                "_async_turn_on_lights should be called when house goes active"
            )
            context = h.coordinator._get_context()
            assert context["is_house_active"] is True
        finally:
            await h.cleanup()

    async def test_house_inactive_in_auto_keeps_current_brightness(
        self, hass: HomeAssistant
    ) -> None:
        """AUTO + house goes inactive -- keeps current brightness."""
        h = await _create_house_harness(hass, initial_house_active="on")
        try:
            await h.motion_on()
            await h.light_on("light.ceiling", brightness=204)
            await h.motion_off()
            h.assert_state(STATE_AUTO)

            spy, called = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy

            await h.set_house_active(False)

            h.assert_state(STATE_AUTO)
            assert not called["value"], (
                "_async_turn_on_lights should NOT be called when house goes inactive"
            )
        finally:
            await h.cleanup()

    async def test_house_active_in_auto_adjusts_brightness(
        self, hass: HomeAssistant
    ) -> None:
        """AUTO + house becomes active -- re-applies brightness."""
        h = await _create_house_harness(hass, initial_house_active="off")
        try:
            await h.motion_on()
            await h.light_on("light.ceiling", brightness=26)
            await h.motion_off()
            h.assert_state(STATE_AUTO)

            spy, called = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy

            await h.set_house_active(True)

            h.assert_state(STATE_AUTO)
            assert called["value"], (
                "_async_turn_on_lights should be called when house goes active"
            )
        finally:
            await h.cleanup()

    async def test_house_inactive_in_manual_keeps_brightness(
        self, hass: HomeAssistant
    ) -> None:
        """MANUAL + house goes inactive -- keeps current brightness."""
        h = await _create_house_harness(hass, initial_house_active="on")
        try:
            await h.light_on("light.ceiling", brightness=204)
            h.force_state(STATE_MANUAL)

            spy, called = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy

            await h.set_house_active(False)

            h.assert_state(STATE_MANUAL)
            assert not called["value"], (
                "_async_turn_on_lights should NOT be called when house goes inactive"
            )
        finally:
            await h.cleanup()

    async def test_house_active_in_manual_adjusts_brightness(
        self, hass: HomeAssistant
    ) -> None:
        """MANUAL + house becomes active -- adjusts brightness."""
        h = await _create_house_harness(hass, initial_house_active="off")
        try:
            await h.light_on("light.ceiling", brightness=26)
            h.force_state(STATE_MANUAL)

            spy, called = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy

            await h.set_house_active(True)

            h.assert_state(STATE_MANUAL)
            assert called["value"], (
                "_async_turn_on_lights should be called when house goes active"
            )
        finally:
            await h.cleanup()

    async def test_house_inactive_in_motion_manual_keeps_brightness(
        self, hass: HomeAssistant
    ) -> None:
        """MOTION_MANUAL + house goes inactive -- keeps current brightness."""
        h = await _create_house_harness(hass, initial_house_active="on")
        try:
            await h.motion_on()
            await h.light_on("light.ceiling", brightness=204)
            h.force_state(STATE_MOTION_MANUAL)

            spy, called = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy

            await h.set_house_active(False)

            h.assert_state(STATE_MOTION_MANUAL)
            assert not called["value"], (
                "_async_turn_on_lights should NOT be called when house goes inactive"
            )
        finally:
            await h.cleanup()

    async def test_house_active_in_motion_manual_adjusts_brightness(
        self, hass: HomeAssistant
    ) -> None:
        """MOTION_MANUAL + house becomes active -- adjusts brightness."""
        h = await _create_house_harness(hass, initial_house_active="off")
        try:
            await h.motion_on()
            await h.light_on("light.ceiling", brightness=26)
            h.force_state(STATE_MOTION_MANUAL)

            spy, called = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy

            await h.set_house_active(True)

            h.assert_state(STATE_MOTION_MANUAL)
            assert called["value"], (
                "_async_turn_on_lights should be called when house goes active"
            )
        finally:
            await h.cleanup()

    async def test_house_change_in_overridden_no_effect(
        self, hass: HomeAssistant
    ) -> None:
        """OVERRIDDEN ignores house active changes entirely."""
        h = await _create_house_harness(hass, initial_house_active="on")
        try:
            h.force_state(STATE_OVERRIDDEN)

            spy, called = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy

            await h.set_house_active(False)

            h.assert_state(STATE_OVERRIDDEN)
            assert not called["value"], (
                "_async_turn_on_lights should NOT be called in OVERRIDDEN state"
            )

            called["value"] = False
            await h.set_house_active(True)

            h.assert_state(STATE_OVERRIDDEN)
            assert not called["value"], (
                "_async_turn_on_lights should NOT be called in OVERRIDDEN state"
            )
        finally:
            await h.cleanup()

    async def test_house_change_in_manual_off_no_effect(
        self, hass: HomeAssistant
    ) -> None:
        """MANUAL_OFF has no lights to adjust -- house active changes ignored."""
        h = await _create_house_harness(hass, initial_house_active="on")
        try:
            h.force_state(STATE_MANUAL_OFF)

            spy, called = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy

            await h.set_house_active(False)

            h.assert_state(STATE_MANUAL_OFF)
            assert not called["value"], (
                "_async_turn_on_lights should NOT be called in MANUAL_OFF state"
            )

            called["value"] = False
            await h.set_house_active(True)

            h.assert_state(STATE_MANUAL_OFF)
            assert not called["value"], (
                "_async_turn_on_lights should NOT be called in MANUAL_OFF state"
            )
        finally:
            await h.cleanup()


# ===================================================================
# 2. House Active With Ambient Light
# ===================================================================


class TestHouseActiveWithAmbientLight:
    """Test interaction between house active state and ambient light sensor.

    The brightness strategy returns:
    - 0 if ambient light is bright (regardless of house active)
    - brightness_active (80%) if dark and house active
    - brightness_inactive (10%) if dark and house inactive
    """

    async def test_house_inactive_dark_motion_uses_inactive_brightness(
        self, hass: HomeAssistant
    ) -> None:
        """Dark + house inactive + motion -> lights at inactive brightness."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_house_active="off",
            initial_ambient="10",
        )
        try:
            context = h.coordinator._get_context()
            assert context["is_house_active"] is False
            assert context["is_dark_inside"] is True

            strategy = h.coordinator.light_controller._brightness_strategy
            brightness = strategy.get_brightness(context)
            assert brightness == 10, (
                f"Expected inactive brightness 10, got {brightness}"
            )
        finally:
            await h.cleanup()

    async def test_house_active_dark_motion_uses_active_brightness(
        self, hass: HomeAssistant
    ) -> None:
        """Dark + house active + motion -> lights at active brightness."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_house_active="on",
            initial_ambient="10",
        )
        try:
            context = h.coordinator._get_context()
            assert context["is_house_active"] is True
            assert context["is_dark_inside"] is True

            strategy = h.coordinator.light_controller._brightness_strategy
            brightness = strategy.get_brightness(context)
            assert brightness == 80, f"Expected active brightness 80, got {brightness}"
        finally:
            await h.cleanup()

    async def test_house_active_bright_no_lights(self, hass: HomeAssistant) -> None:
        """Bright ambient + house active -> strategy returns 0 (no lights)."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_house_active="on",
            initial_ambient="100",
        )
        try:
            # Need to initialize hysteresis by triggering _get_context
            await h.motion_on()
            h.force_state(STATE_IDLE)

            context = h.coordinator._get_context()
            assert context["is_house_active"] is True
            assert context["is_dark_inside"] is False

            strategy = h.coordinator.light_controller._brightness_strategy
            brightness = strategy.get_brightness(context)
            assert brightness == 0, (
                f"Expected 0 brightness when bright, got {brightness}"
            )
        finally:
            await h.cleanup()

    async def test_house_inactive_bright_no_lights(self, hass: HomeAssistant) -> None:
        """Bright ambient + house inactive -> strategy returns 0 (no lights)."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_house_active="off",
            initial_ambient="100",
        )
        try:
            # Need to initialize hysteresis by triggering _get_context
            await h.motion_on()
            h.force_state(STATE_IDLE)

            context = h.coordinator._get_context()
            assert context["is_house_active"] is False
            assert context["is_dark_inside"] is False

            strategy = h.coordinator.light_controller._brightness_strategy
            brightness = strategy.get_brightness(context)
            assert brightness == 0, (
                f"Expected 0 brightness when bright, got {brightness}"
            )
        finally:
            await h.cleanup()


# ===================================================================
# 3. House Active With Motion
# ===================================================================


class TestHouseActiveWithMotion:
    """Test full motion cycles with different house active states."""

    async def test_motion_with_house_active_uses_full_brightness(
        self, hass: HomeAssistant
    ) -> None:
        """Full motion cycle with house active uses active brightness."""
        h = await _create_house_harness(hass, initial_house_active="on")
        try:
            h.assert_state(STATE_IDLE)

            context = h.coordinator._get_context()
            assert context["is_house_active"] is True

            strategy = h.coordinator.light_controller._brightness_strategy
            brightness = strategy.get_brightness(context)
            assert brightness == 80, f"Expected active brightness 80, got {brightness}"

            # Full motion cycle
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            await h.motion_off()
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")

            await h.expire_timer("motion")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_motion_with_house_inactive_uses_dim_brightness(
        self, hass: HomeAssistant
    ) -> None:
        """Full motion cycle with house inactive uses inactive brightness."""
        h = await _create_house_harness(hass, initial_house_active="off")
        try:
            h.assert_state(STATE_IDLE)

            context = h.coordinator._get_context()
            assert context["is_house_active"] is False

            strategy = h.coordinator.light_controller._brightness_strategy
            brightness = strategy.get_brightness(context)
            assert brightness == 10, (
                f"Expected inactive brightness 10, got {brightness}"
            )

            # Full motion cycle
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            await h.motion_off()
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")

            await h.expire_timer("motion")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_house_changes_mid_motion_cycle(self, hass: HomeAssistant) -> None:
        """House active changes while motion is active.

        Start active, trigger motion, go inactive mid-cycle (keeps brightness),
        then go active again (re-applies brightness).
        """
        h = await _create_house_harness(hass, initial_house_active="on")
        try:
            # Motion on with house active
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
            await h.light_on("light.ceiling", brightness=204)

            context = h.coordinator._get_context()
            assert context["is_house_active"] is True

            # House goes inactive mid-motion -- keeps current brightness
            spy_inactive, called_inactive = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy_inactive

            await h.set_house_active(False)
            h.assert_state(STATE_MOTION_AUTO)
            assert not called_inactive["value"], (
                "Should NOT re-apply brightness when going inactive"
            )
            context = h.coordinator._get_context()
            assert context["is_house_active"] is False

            # House goes active again -- re-applies brightness
            spy_active, called_active = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy_active

            await h.set_house_active(True)
            h.assert_state(STATE_MOTION_AUTO)
            assert called_active["value"], (
                "Should re-apply brightness when going active"
            )
            context = h.coordinator._get_context()
            assert context["is_house_active"] is True
        finally:
            await h.cleanup()


# ===================================================================
# 4. House Active No Change
# ===================================================================


class TestHouseActiveNoChange:
    """Test that redundant house active changes are ignored."""

    async def test_same_state_no_action(self, hass: HomeAssistant) -> None:
        """House active on -> on (no actual change) is ignored."""
        h = await _create_house_harness(hass, initial_house_active="on")
        try:
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
            await h.light_on("light.ceiling", brightness=204)

            spy, called = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy

            # Set to same state (on -> on)
            await h.set_house_active(True)

            assert not called["value"], (
                "_async_turn_on_lights should NOT be called for same-state change"
            )
            h.assert_state(STATE_MOTION_AUTO)
        finally:
            await h.cleanup()

    async def test_lights_off_house_active_changes_no_effect(
        self, hass: HomeAssistant
    ) -> None:
        """If no lights are on, house active change has no brightness effect.

        Even in states that normally adjust brightness (AUTO, MOTION_AUTO),
        if lights are off, _async_turn_on_lights is not called.
        """
        h = await _create_house_harness(hass, initial_house_active="on")
        try:
            # Get into MOTION_AUTO but with lights still off
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
            # Lights are off (no light_on call)
            h.assert_lights_off()

            spy, called = _make_turn_on_spy(h)
            h.coordinator._async_turn_on_lights = spy

            await h.set_house_active(False)

            assert not called["value"], (
                "_async_turn_on_lights should NOT be called when lights are off"
            )

            called["value"] = False
            await h.set_house_active(True)

            assert not called["value"], (
                "_async_turn_on_lights should NOT be called when lights are off"
            )
        finally:
            await h.cleanup()
