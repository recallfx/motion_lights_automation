"""Tests simulating complete real-world usage scenarios.

Each test tells a story of how a user would actually interact with the
system over time.  These are multi-step end-to-end tests that exercise
many coordinator subsystems together.
"""

from __future__ import annotations

from homeassistant.core import Context, HomeAssistant

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_HOUSE_ACTIVE,
    CONF_LIGHTS,
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


def _make_turn_off_spy(harness: CoordinatorHarness):
    """Return (spy_fn, was_called) pair.

    Simulates lights going off with a tracked integration context so the
    light-change handler fires LIGHTS_ALL_OFF instead of
    MANUAL_OFF_INTERVENTION.
    """
    called = {"value": False}

    async def spy():
        called["value"] = True
        for light_id in harness.coordinator.light_controller.lights:
            ctx = Context()
            harness.coordinator.light_controller._context_tracking.add(ctx.id)
            harness.hass.states.async_set(light_id, "off", context=ctx)

    return spy, called


# ===================================================================
# TestEveningRoutine
# ===================================================================


class TestEveningRoutine:
    """Long multi-step scenarios simulating a typical evening."""

    async def test_coming_home_evening(self, hass: HomeAssistant) -> None:
        """Simulate arriving home in the evening.

        1. IDLE, dark outside, house inactive
        2. House becomes active (someone arrives home)
        3. Motion detected -> MOTION_AUTO, lights on
        4. Motion clears -> AUTO (timer starts)
        5. Motion detected again -> MOTION_AUTO (timer cancelled)
        6. User adjusts brightness -> MOTION_MANUAL
        7. Motion clears -> MANUAL (extended timer)
        8. Extended timer expires -> IDLE
        """
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_LIGHTS: ["light.ceiling", "light.lamp"],
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_lights={
                "light.ceiling": {"state": "off"},
                "light.lamp": {"state": "off"},
            },
            initial_ambient="20",
            initial_house_active="off",
        )
        try:
            # 1. Start: IDLE, dark outside (lux=20), house inactive
            h.assert_state(STATE_IDLE)

            # 2. House becomes active (someone arrives home)
            await h.set_house_active(True)
            h.assert_state(STATE_IDLE)

            # 3. Motion detected in hallway -> MOTION_AUTO
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            # 4. Motion clears -> AUTO (timer starts)
            await h.motion_off()
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")

            # 5. Motion detected in living room -> MOTION_AUTO (timer cancelled)
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
            h.assert_timer_inactive("motion")

            # 6. User adjusts brightness -> MOTION_MANUAL
            await h.manual_brightness_change("light.ceiling", brightness=150)
            h.assert_state(STATE_MOTION_MANUAL)

            # 7. Motion clears -> MANUAL (extended timer)
            await h.motion_off()
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")

            # 8. Extended timer expires -> IDLE
            await h.expire_timer("extended")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_watching_tv_override(self, hass: HomeAssistant) -> None:
        """Simulate watching TV with override switch.

        1. IDLE, dark, house active
        2. Motion -> lights on
        3. User turns on override switch -> OVERRIDDEN
        4. Motion on/off cycles -> no state changes
        5. User turns off override -> MANUAL (lights still on) or IDLE
        """
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_OVERRIDE_SWITCH: "switch.override",
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
            },
        )
        try:
            # 1. Start: IDLE, house active
            h.assert_state(STATE_IDLE)

            # 2. Motion -> lights on (MOTION_AUTO)
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            # Put lights on so override off can go to MANUAL
            await h.light_on("light.ceiling", brightness=200)

            # 3. User turns on override -> OVERRIDDEN
            await h.override_on()
            h.assert_state(STATE_OVERRIDDEN)
            h.assert_no_active_timers()

            # 4. Motion on/off cycles -> still OVERRIDDEN
            await h.motion_off()
            h.assert_state(STATE_OVERRIDDEN)

            await h.motion_on()
            h.assert_state(STATE_OVERRIDDEN)

            await h.motion_off()
            h.assert_state(STATE_OVERRIDDEN)

            # 5. User turns off override with lights still on -> MANUAL
            h.refresh_lights()
            await h.override_off()
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")
        finally:
            await h.cleanup()

    async def test_going_to_bed(self, hass: HomeAssistant) -> None:
        """Simulate going to bed.

        1. MANUAL (user has lights on), house active
        2. House becomes inactive (bedtime)
        3. User turns off lights manually -> MANUAL_OFF
        4. Motion detected (walking to bedroom) -> stays MANUAL_OFF
        5. Motion clears
        6. Extended timer expires -> IDLE
        """
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_HOUSE_ACTIVE: "input_boolean.house_active",
            },
        )
        try:
            # 1. Start: user has lights on manually -> MANUAL
            await h.manual_light_on("light.ceiling", brightness=200)
            h.assert_state(STATE_MANUAL)

            # 2. House becomes inactive (bedtime)
            await h.set_house_active(False)
            # State doesn't change, just affects brightness calculations
            h.assert_state(STATE_MANUAL)

            # 3. User turns off lights manually -> MANUAL_OFF
            await h.manual_light_off("light.ceiling")
            h.assert_state(STATE_MANUAL_OFF)
            h.assert_timer_active("extended")

            # 4. Motion detected (walking to bedroom) -> stays MANUAL_OFF
            await h.motion_on()
            h.assert_state(STATE_MANUAL_OFF)

            # 5. Motion clears -> extended timer restarts
            await h.motion_off()
            h.assert_state(STATE_MANUAL_OFF)
            h.assert_timer_active("extended")

            # 6. Extended timer expires -> IDLE
            await h.expire_timer("extended")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()


# ===================================================================
# TestDaylightTransitions
# ===================================================================


class TestDaylightTransitions:
    """Scenarios around dawn/dusk ambient light changes.

    Note on hysteresis: The coordinator uses +-20 lux hysteresis around
    the configured threshold.  With threshold=50: low=30, high=70.
    The ambient handler evaluates _get_context() (new lux) BEFORE
    _evaluate_darkness_from_state(old_state), both of which mutate the
    shared _brightness_mode_is_dim flag.  Therefore the ambient handler
    only fires when a single lux-change event crosses *both* the old
    and new evaluations to different results -- which requires the old
    value to be far enough from the crossing boundary.
    """

    async def test_morning_brightening(self, hass: HomeAssistant) -> None:
        """Simulate morning brightening turning off lights.

        1. IDLE, dark (lux=10), house active
        2. Motion detected -> MOTION_AUTO, lights on
        3. Lux rises within hysteresis band (stays dark)
        4. Lux crosses high threshold from a value <= low threshold ->
           lights turn off -> IDLE
        5. More motion -> MOTION_AUTO but brightness=0 (too bright)

        The ambient handler requires old_lux <= low_threshold (30) for
        dark-to-bright transitions to be detected, due to the shared
        mutable hysteresis state.
        """
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_ambient="10",
        )
        try:
            # 1. Start: IDLE, dark
            h.assert_state(STATE_IDLE)

            # 2. Motion -> MOTION_AUTO, initializes hysteresis as DIM (10 < 50)
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            # Simulate lights being on
            await h.light_on("light.ceiling", brightness=200)

            # 3. Lux rises to 40 - still within hysteresis band (< 70)
            await h.set_ambient_lux(40)
            h.assert_state(STATE_MOTION_AUTO, msg="40 lux - still dark (< 70)")

            # Set lux to a value at or below the low threshold (30) so the
            # next jump to 80 is detected as a dark-to-bright crossing.
            await h.set_ambient_lux(25)
            h.assert_state(STATE_MOTION_AUTO, msg="25 lux - still dark")

            # 4. Lux jumps to 80: the ambient handler evaluates new=80 (>=70,
            #    switches BRIGHT) then old=25 (<=30, switches back to DIM).
            #    old_is_dark=True, is_dark_now=False -> change detected!
            #    MOTION_AUTO + bright -> turns off lights -> IDLE
            spy, called = _make_turn_off_spy(h)
            h.coordinator._async_turn_off_lights = spy

            await h.set_ambient_lux(80)
            await hass.async_block_till_done()

            assert called["value"], "Expected lights to turn off when bright"
            h.assert_state(STATE_IDLE)

            # 5. New motion cycle -> MOTION_AUTO but brightness=0 (too bright)
            #    Must clear motion first since sensor is still "on" from before
            await h.motion_off()
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            # Verify context says it's bright
            context = h.coordinator._get_context()
            assert context["is_dark_inside"] is False
        finally:
            await h.cleanup()

    async def test_evening_darkening(self, hass: HomeAssistant) -> None:
        """Simulate evening darkening triggering lights.

        1. IDLE, bright (lux=100), house active
        2. Motion detected -> MOTION_AUTO but brightness=0 (too bright)
        3. Lux drops within hysteresis band (stays bright)
        4. Lux crosses low threshold from a value >= high threshold ->
           dark + motion -> MOTION_AUTO

        The ambient handler requires old_lux >= high_threshold (70) for
        bright-to-dark transitions to be detected.
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
            # 1. Start: IDLE, bright
            h.assert_state(STATE_IDLE)

            # 2. Motion detected -> MOTION_AUTO (initializes hysteresis as BRIGHT)
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            # Force back to IDLE, keep motion sensor on
            h.force_state(STATE_IDLE)

            # 3. Lux within hysteresis band (still bright, > 30)
            await h.set_ambient_lux(50)
            h.assert_state(STATE_IDLE, msg="50 lux - still bright (> 30)")

            # Set lux back to a value at or above the high threshold (70) so
            # the next drop to 29 is detected as a bright-to-dark crossing.
            await h.set_ambient_lux(75)
            h.assert_state(STATE_IDLE, msg="75 lux - still bright")

            # 4. Lux drops to 29: the ambient handler evaluates new=29 (<=30,
            #    switches DIM) then old=75 (>=70, switches back to BRIGHT).
            #    old_is_dark=False, is_dark_now=True -> change detected!
            #    IDLE + motion active + dark -> MOTION_ON -> MOTION_AUTO
            await h.set_ambient_lux(29)
            h.assert_state(STATE_MOTION_AUTO)
        finally:
            await h.cleanup()

    async def test_cloudy_day_fluctuations(self, hass: HomeAssistant) -> None:
        """Simulate cloudy day: bright -> dark (clouds) -> bright (clears).

        1. Start bright (lux=80), motion active
        2. Clouds: lux drops to 29 -> dark, lights on
        3. Sun peek: lux back to 55 -- within hysteresis, stays dark
        4. Clear: lux to 75 from a value <= 30 -> bright, lights off
        """
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
                CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            },
            initial_ambient="80",
        )
        try:
            # Initialize hysteresis (BRIGHT mode via motion_on at 80 lux)
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            # Force back to IDLE, keep motion sensor on
            h.force_state(STATE_IDLE)

            # 2. Clouds: lux drops to 29 -> crosses low threshold (30) -> dark
            #    IDLE + motion active + dark -> MOTION_AUTO
            await h.set_ambient_lux(29)
            h.assert_state(STATE_MOTION_AUTO)

            # Get lights on for the bright transition
            await h.light_on("light.ceiling", brightness=200)

            # Move to AUTO so we can test bright turn-off
            await h.motion_off()
            h.assert_state(STATE_AUTO)

            # 3. Sun peek: lux to 55 -- within hysteresis (< 70), stays dark
            await h.set_ambient_lux(55)
            h.assert_state(STATE_AUTO, msg="55 lux - still dark (< 70)")

            # Set lux back to a value <= low threshold so the next bright
            # crossing is detected (old <= 30 switches back to DIM)
            await h.set_ambient_lux(25)
            h.assert_state(STATE_AUTO, msg="25 lux - still dark")

            # 4. Clear: lux to 75 -> above high threshold (70) -> bright
            #    new=75 (>=70, switches BRIGHT), old=25 (<=30, switches DIM)
            #    old_is_dark=True, is_dark_now=False -> change detected!
            spy, called = _make_turn_off_spy(h)
            h.coordinator._async_turn_off_lights = spy

            await h.set_ambient_lux(75)
            await hass.async_block_till_done()

            assert called["value"], "Expected lights to turn off when bright"
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()


# ===================================================================
# TestMultiRoomScenarios
# ===================================================================


class TestMultiRoomScenarios:
    """Scenarios with multiple motion sensors."""

    async def test_walking_between_rooms(self, hass: HomeAssistant) -> None:
        """Simulate walking between rooms with two motion sensors.

        1. IDLE with 2 motion sensors
        2. Sensor 1 on -> MOTION_AUTO
        3. Sensor 2 on -> still MOTION_AUTO
        4. Sensor 1 off -> still MOTION_AUTO (sensor 2 still on)
        5. Sensor 2 off -> AUTO (all sensors off)
        6. Timer expires -> IDLE
        """
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_ENTITY: [
                    "binary_sensor.hallway",
                    "binary_sensor.living_room",
                ],
            },
        )
        try:
            # 1. Start: IDLE
            h.assert_state(STATE_IDLE)

            # 2. Sensor 1 on -> MOTION_AUTO
            await h.motion_on("binary_sensor.hallway")
            h.assert_state(STATE_MOTION_AUTO)

            # 3. Sensor 2 on -> still MOTION_AUTO
            await h.motion_on("binary_sensor.living_room")
            h.assert_state(STATE_MOTION_AUTO)

            # 4. Sensor 1 off -> still MOTION_AUTO (sensor 2 still on)
            await h.motion_off("binary_sensor.hallway")
            h.assert_state(STATE_MOTION_AUTO)

            # 5. Sensor 2 off -> AUTO
            await h.motion_off("binary_sensor.living_room")
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")

            # 6. Timer expires -> IDLE
            await h.expire_timer("motion")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_quick_pass_through(self, hass: HomeAssistant) -> None:
        """Simulate someone walking past without stopping.

        1. IDLE, motion delay = 5s
        2. Motion on -> delay timer starts
        3. Motion off before delay expires -> delay cancelled, stays IDLE
        """
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_MOTION_DELAY: 5,
            },
        )
        try:
            # 1. Start: IDLE
            h.assert_state(STATE_IDLE)

            # 2. Motion on -> delay timer starts, state stays IDLE
            await h.motion_on()
            h.assert_state(STATE_IDLE)
            h.assert_timer_active("motion_delay")

            # 3. Motion off before delay -> delay cancelled, stays IDLE
            await h.motion_off()
            h.assert_timer_inactive("motion_delay")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()


# ===================================================================
# TestManualInterventionScenarios
# ===================================================================


class TestManualInterventionScenarios:
    """Complex manual intervention stories."""

    async def test_user_takes_control_then_leaves(self, hass: HomeAssistant) -> None:
        """Simulate user taking manual control then leaving.

        1. MOTION_AUTO (motion active, lights on)
        2. User adjusts brightness -> MOTION_MANUAL
        3. User adjusts again -> stays MOTION_MANUAL
        4. Motion clears -> MANUAL (extended timer)
        5. User turns off all lights -> MANUAL_OFF
        6. Extended timer expires -> IDLE
        """
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_LIGHTS: ["light.ceiling", "light.lamp"],
            },
            initial_lights={
                "light.ceiling": {"state": "off"},
                "light.lamp": {"state": "off"},
            },
        )
        try:
            # 1. Motion detected -> MOTION_AUTO with lights on
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
            await h.light_on("light.ceiling", brightness=200)
            await h.light_on("light.lamp", brightness=200)

            # 2. User adjusts brightness -> MOTION_MANUAL
            await h.manual_brightness_change("light.ceiling", brightness=150)
            h.assert_state(STATE_MOTION_MANUAL)

            # 3. User adjusts again -> stays MOTION_MANUAL
            await h.manual_brightness_change("light.lamp", brightness=100)
            h.assert_state(STATE_MOTION_MANUAL)

            # 4. Motion clears -> MANUAL (extended timer)
            await h.motion_off()
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")

            # 5. User turns off one light -> stays MANUAL (restarts timer)
            await h.manual_light_off("light.lamp")
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")

            # User turns off remaining light -> MANUAL_OFF
            await h.manual_light_off("light.ceiling")
            h.assert_state(STATE_MANUAL_OFF)

            # 6. Extended timer expires -> IDLE
            await h.expire_timer("extended")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_user_fights_automation(self, hass: HomeAssistant) -> None:
        """Simulate user turning off auto-controlled lights repeatedly.

        1. IDLE
        2. Motion -> MOTION_AUTO, lights on
        3. User turns off all lights -> MANUAL_OFF
        4. Motion still active -> stays MANUAL_OFF (respects user)
        5. Motion clears -> MANUAL_OFF (extended timer running)
        6. Motion returns -> stays MANUAL_OFF
        7. Extended timer expires -> IDLE
        8. Motion detected again -> MOTION_AUTO (new cycle)
        """
        h = await CoordinatorHarness.create(hass)
        try:
            # 1. Start: IDLE
            h.assert_state(STATE_IDLE)

            # 2. Motion -> MOTION_AUTO
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
            await h.light_on("light.ceiling", brightness=200)

            # 3. User turns off all lights -> MANUAL_OFF
            await h.manual_light_off("light.ceiling")
            h.assert_state(STATE_MANUAL_OFF)

            # 4. Motion still active -> stays MANUAL_OFF
            # (motion was already on, no new event needed)
            h.assert_state(STATE_MANUAL_OFF)

            # 5. Motion clears -> MANUAL_OFF with extended timer
            await h.motion_off()
            h.assert_state(STATE_MANUAL_OFF)
            h.assert_timer_active("extended")

            # 6. Motion returns -> stays MANUAL_OFF
            await h.motion_on()
            h.assert_state(STATE_MANUAL_OFF)

            # Motion clears again
            await h.motion_off()
            h.assert_state(STATE_MANUAL_OFF)

            # 7. Extended timer expires -> IDLE
            await h.expire_timer("extended")
            h.assert_state(STATE_IDLE)

            # 8. Motion detected again -> MOTION_AUTO (fresh cycle)
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
        finally:
            await h.cleanup()

    async def test_user_turns_on_lights_without_motion(
        self, hass: HomeAssistant
    ) -> None:
        """Simulate user manually turning on lights without any motion.

        1. IDLE, no motion
        2. User turns on lights manually -> MANUAL (extended timer)
        3. Motion detected -> MOTION_MANUAL
        4. Motion clears -> MANUAL
        5. Extended timer expires -> IDLE
        """
        h = await CoordinatorHarness.create(hass)
        try:
            # 1. Start: IDLE, no motion
            h.assert_state(STATE_IDLE)

            # 2. User turns on lights manually -> MANUAL
            await h.manual_light_on("light.ceiling", brightness=200)
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")

            # 3. Motion detected -> MOTION_MANUAL
            await h.motion_on()
            h.assert_state(STATE_MOTION_MANUAL)
            # Extended timer cancelled during MOTION_MANUAL
            h.assert_timer_inactive("extended")

            # 4. Motion clears -> MANUAL
            await h.motion_off()
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")

            # 5. Extended timer expires -> IDLE
            await h.expire_timer("extended")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()


# ===================================================================
# TestErrorRecovery
# ===================================================================


class TestErrorRecovery:
    """Scenarios testing recovery from unexpected states."""

    async def test_recover_from_stuck_motion(self, hass: HomeAssistant) -> None:
        """Simulate recovery from a stuck motion sensor.

        1. MOTION_AUTO
        2. Motion sensor stuck on for 30+ minutes
        3. Watchdog fires -> checks sensor, still on -> restarts watchdog
        4. Eventually sensor cleared -> AUTO -> IDLE
        """
        h = await CoordinatorHarness.create(hass)
        try:
            # 1. Start: MOTION_AUTO
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
            assert h.coordinator._motion_watchdog_handle is not None

            # 2-3. Watchdog fires, sensor still on -> restarts watchdog
            await h.coordinator._async_motion_watchdog_fired()
            h.assert_state(STATE_MOTION_AUTO)
            assert h.coordinator._motion_watchdog_handle is not None

            # 4. Eventually sensor clears
            await h.motion_off()
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")

            # Timer expires -> IDLE
            await h.expire_timer("motion")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_reconciliation_after_missed_event(self, hass: HomeAssistant) -> None:
        """Simulate reconciliation detecting all lights off in MOTION_AUTO.

        1. MOTION_AUTO
        2. Somehow lights got turned off (missed KNX event)
        3. Reconciliation fires -> detects all lights off
        4. Transitions to IDLE directly (lights-off drift)
        """
        h = await CoordinatorHarness.create(hass)
        try:
            # 1. Get into MOTION_AUTO
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)

            # 2. Lights off without going through normal handler (missed event)
            hass.states.async_set("light.ceiling", "off")
            h.force_state(STATE_MOTION_AUTO)

            # 3. Reconciliation fires -> detects all lights off in MOTION_AUTO
            await h.coordinator._async_reconcile_state()

            # 4. Lights-off drift: MOTION_AUTO + lights off -> IDLE
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_reconciliation_finds_lights_on_in_idle(
        self, hass: HomeAssistant
    ) -> None:
        """Simulate reconciliation detecting lights on while in IDLE.

        1. IDLE
        2. Somehow a light turned on (missed event)
        3. Reconciliation fires -> detects lights on in IDLE
        4. Transitions to MANUAL
        """
        h = await CoordinatorHarness.create(hass)
        try:
            # 1. Start: IDLE
            h.assert_state(STATE_IDLE)

            # 2. Light turned on without normal handler
            hass.states.async_set("light.ceiling", "on", attributes={"brightness": 200})
            h.force_state(STATE_IDLE)

            # 3. Reconciliation fires
            await h.coordinator._async_reconcile_state()

            # 4. Detects lights on in IDLE -> MANUAL
            h.assert_state(STATE_MANUAL)
            h.assert_event_log_contains("Reconciliation")
        finally:
            await h.cleanup()


# ===================================================================
# TestTimerInteractionScenarios
# ===================================================================


class TestTimerInteractionScenarios:
    """Complex timer interaction stories."""

    async def test_timer_reset_on_repeated_manual_changes(
        self, hass: HomeAssistant
    ) -> None:
        """Simulate user making repeated manual adjustments.

        1. MANUAL, extended timer running
        2. User adjusts brightness -> timer restarted
        3. User adjusts again -> timer restarted again
        4. Eventually user stops -> timer expires -> IDLE
        """
        h = await CoordinatorHarness.create(hass)
        try:
            # Get into MANUAL state
            await h.manual_light_on("light.ceiling", brightness=200)
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")

            # 2. User adjusts brightness -> timer restarted
            await h.manual_brightness_change("light.ceiling", brightness=150)
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")

            # 3. User adjusts again -> timer restarted
            await h.manual_brightness_change("light.ceiling", brightness=100)
            h.assert_state(STATE_MANUAL)
            h.assert_timer_active("extended")

            # 4. Eventually user stops -> timer expires -> IDLE
            await h.expire_timer("extended")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()

    async def test_motion_cancels_auto_timer_repeatedly(
        self, hass: HomeAssistant
    ) -> None:
        """Simulate repeated motion during AUTO state.

        1. AUTO (motion timer running)
        2. Motion on -> MOTION_AUTO (timer cancelled)
        3. Motion off -> AUTO (new timer)
        4. Motion on again -> MOTION_AUTO (timer cancelled)
        5. Motion off -> AUTO (new timer)
        6. Timer expires -> IDLE
        """
        h = await CoordinatorHarness.create(hass)
        try:
            # Get to AUTO
            await h.motion_on()
            await h.motion_off()
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")

            # 2. Motion on -> MOTION_AUTO (timer cancelled)
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
            h.assert_timer_inactive("motion")

            # 3. Motion off -> AUTO (new timer)
            await h.motion_off()
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")

            # 4. Motion on again -> MOTION_AUTO
            await h.motion_on()
            h.assert_state(STATE_MOTION_AUTO)
            h.assert_timer_inactive("motion")

            # 5. Motion off -> AUTO (new timer)
            await h.motion_off()
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")

            # 6. Timer expires -> IDLE
            await h.expire_timer("motion")
            h.assert_state(STATE_IDLE)
        finally:
            await h.cleanup()


# ===================================================================
# TestStartupScenarios
# ===================================================================


class TestStartupScenarios:
    """Startup under various conditions."""

    async def test_startup_everything_off(self, hass: HomeAssistant) -> None:
        """Clean start, all off -> IDLE."""
        h = await CoordinatorHarness.create(
            hass,
            skip_grace_period=False,
        )
        try:
            h.assert_state(STATE_IDLE)
            h.assert_event_log_contains("restarted")
        finally:
            await h.cleanup()

    async def test_startup_lights_on_motion_on(self, hass: HomeAssistant) -> None:
        """Lights on + motion active at startup -> MOTION_AUTO."""
        h = await CoordinatorHarness.create(
            hass,
            initial_motion="on",
            initial_lights={
                "light.ceiling": {"state": "on", "brightness": 200},
            },
            skip_grace_period=False,
        )
        try:
            h.assert_state(STATE_MOTION_AUTO)
            h.assert_event_log_contains("restarted")
        finally:
            await h.cleanup()

    async def test_startup_lights_on_motion_off(self, hass: HomeAssistant) -> None:
        """Lights on, no motion at startup -> AUTO (starts timer)."""
        h = await CoordinatorHarness.create(
            hass,
            initial_lights={
                "light.ceiling": {"state": "on", "brightness": 200},
            },
            skip_grace_period=False,
        )
        try:
            h.assert_state(STATE_AUTO)
            h.assert_timer_active("motion")
            h.assert_event_log_contains("restarted")
        finally:
            await h.cleanup()

    async def test_startup_override_active(self, hass: HomeAssistant) -> None:
        """Override switch on at startup -> OVERRIDDEN."""
        h = await CoordinatorHarness.create(
            hass,
            config_data={
                CONF_OVERRIDE_SWITCH: "switch.override",
            },
            initial_override="on",
            skip_grace_period=False,
        )
        try:
            h.assert_state(STATE_OVERRIDDEN)
            h.assert_event_log_contains("restarted")
        finally:
            await h.cleanup()
