"""Shared fixtures and test harness for pipeline tests.

Provides CoordinatorHarness - a helper that wraps MotionLightsCoordinator
with convenient methods for simulating HA events and asserting state.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.motion_lights_automation.const import (
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_AMBIENT_LIGHT_THRESHOLD,
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_EXTENDED_TIMEOUT,
    CONF_HOUSE_ACTIVE,
    CONF_LIGHTS,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_DELAY,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
    DOMAIN,
)
from custom_components.motion_lights_automation.motion_coordinator import (
    MotionLightsCoordinator,
)


class CoordinatorHarness:
    """Test harness wrapping MotionLightsCoordinator for easy testing.

    Usage:
        harness = await CoordinatorHarness.create(hass, config_data={...})
        await harness.motion_on()
        harness.assert_state(STATE_MOTION_AUTO)
        await harness.motion_off()
        harness.assert_state(STATE_AUTO)
        harness.assert_timer_active("motion")
    """

    def __init__(self, hass: HomeAssistant, coordinator: MotionLightsCoordinator):
        self.hass = hass
        self.coordinator = coordinator

    @classmethod
    async def create(
        cls,
        hass: HomeAssistant,
        config_data: dict[str, Any] | None = None,
        initial_motion: str = "off",
        initial_lights: dict[str, dict[str, Any]] | None = None,
        initial_override: str | None = None,
        initial_ambient: str | None = None,
        initial_house_active: str | None = None,
        skip_grace_period: bool = True,
    ) -> CoordinatorHarness:
        """Create a harness with coordinator and initial entity states.

        Args:
            hass: HomeAssistant instance
            config_data: Config overrides (merged with defaults)
            initial_motion: Initial motion sensor state ("on"/"off")
            initial_lights: Dict of {entity_id: {"state": "on"/"off", "brightness": N}}
            initial_override: Initial override switch state or None to skip
            initial_ambient: Initial ambient sensor value or None to skip
            initial_house_active: Initial house active state or None to skip
            skip_grace_period: Whether to skip the startup grace period
        """
        data = _build_config(config_data or {})
        entry = _build_entry(data)

        # Set up motion sensors
        motion_entities = data.get(CONF_MOTION_ENTITY, [])
        if isinstance(motion_entities, str):
            motion_entities = [motion_entities]
        for entity_id in motion_entities:
            hass.states.async_set(entity_id, initial_motion)

        # Set up lights
        light_entities = data.get(CONF_LIGHTS, [])
        if isinstance(light_entities, str):
            light_entities = [light_entities]
        if initial_lights:
            for entity_id, attrs in initial_lights.items():
                state = attrs.get("state", "off")
                ha_attrs = {}
                if "brightness" in attrs:
                    ha_attrs["brightness"] = attrs["brightness"]
                hass.states.async_set(entity_id, state, attributes=ha_attrs)
        else:
            for entity_id in light_entities:
                hass.states.async_set(entity_id, "off")

        # Set up override switch
        if data.get(CONF_OVERRIDE_SWITCH):
            hass.states.async_set(
                data[CONF_OVERRIDE_SWITCH],
                initial_override or "off",
            )

        # Set up ambient light sensor
        if data.get(CONF_AMBIENT_LIGHT_SENSOR):
            ambient_val = initial_ambient or "100"
            hass.states.async_set(
                data[CONF_AMBIENT_LIGHT_SENSOR],
                ambient_val,
                attributes={"unit_of_measurement": "lx"},
            )

        # Set up house active entity
        if data.get(CONF_HOUSE_ACTIVE):
            hass.states.async_set(
                data[CONF_HOUSE_ACTIVE],
                initial_house_active or "on",
            )

        coordinator = MotionLightsCoordinator(hass, entry)
        await coordinator.async_setup_listeners()

        if skip_grace_period:
            coordinator._startup_time = dt_util.now() - timedelta(seconds=200)

        harness = cls(hass, coordinator)
        return harness

    async def cleanup(self) -> None:
        """Clean up coordinator listeners."""
        self.coordinator.async_cleanup_listeners()

    # -- State assertions --

    @property
    def state(self) -> str:
        return self.coordinator.current_state

    def assert_state(self, expected: str, msg: str = "") -> None:
        actual = self.coordinator.current_state
        detail = f" ({msg})" if msg else ""
        assert actual == expected, (
            f"Expected state '{expected}' but got '{actual}'{detail}"
        )

    def assert_timer_active(self, name: str) -> None:
        assert self.coordinator.timer_manager.has_active_timer(name), (
            f"Expected timer '{name}' to be active"
        )

    def assert_timer_inactive(self, name: str) -> None:
        assert not self.coordinator.timer_manager.has_active_timer(name), (
            f"Expected timer '{name}' to be inactive"
        )

    def assert_no_active_timers(self) -> None:
        active = self.coordinator.timer_manager.get_active_timers()
        assert len(active) == 0, (
            f"Expected no active timers but found: {[t.name for t in active]}"
        )

    def assert_event_log_contains(self, substring: str) -> None:
        matches = [
            msg
            for msg in self.coordinator._event_log
            if substring.lower() in msg.lower()
        ]
        assert len(matches) > 0, (
            f"Expected event log to contain '{substring}'. "
            f"Got: {self.coordinator._event_log}"
        )

    def assert_lights_on(self) -> None:
        assert self.coordinator.light_controller.any_lights_on(refresh=True), (
            "Expected at least one light to be on"
        )

    def assert_lights_off(self) -> None:
        assert not self.coordinator.light_controller.any_lights_on(refresh=True), (
            "Expected all lights to be off"
        )

    # -- Entity simulators --

    async def motion_on(self, entity_id: str = "binary_sensor.motion") -> None:
        """Simulate motion detected."""
        self.hass.states.async_set(entity_id, "on")
        await self.hass.async_block_till_done()

    async def motion_off(self, entity_id: str = "binary_sensor.motion") -> None:
        """Simulate motion cleared."""
        self.hass.states.async_set(entity_id, "off")
        await self.hass.async_block_till_done()

    async def light_on(
        self, entity_id: str = "light.ceiling", brightness: int = 200
    ) -> None:
        """Simulate a light turning on (integration-controlled)."""
        self.hass.states.async_set(
            entity_id, "on", attributes={"brightness": brightness}
        )
        await self.hass.async_block_till_done()

    async def light_off(self, entity_id: str = "light.ceiling") -> None:
        """Simulate a light turning off (integration-controlled)."""
        self.hass.states.async_set(entity_id, "off")
        await self.hass.async_block_till_done()

    async def manual_light_on(
        self, entity_id: str = "light.ceiling", brightness: int = 200
    ) -> None:
        """Simulate user manually turning on a light."""
        with patch.object(
            self.coordinator.light_controller,
            "is_integration_context",
            return_value=False,
        ):
            self.hass.states.async_set(
                entity_id, "on", attributes={"brightness": brightness}
            )
            await self.hass.async_block_till_done()

    async def manual_light_off(self, entity_id: str = "light.ceiling") -> None:
        """Simulate user manually turning off a light."""
        with patch.object(
            self.coordinator.light_controller,
            "is_integration_context",
            return_value=False,
        ):
            self.hass.states.async_set(entity_id, "off")
            await self.hass.async_block_till_done()

    async def manual_brightness_change(
        self, entity_id: str = "light.ceiling", brightness: int = 100
    ) -> None:
        """Simulate user changing brightness on an already-on light."""
        with patch.object(
            self.coordinator.light_controller,
            "is_integration_context",
            return_value=False,
        ):
            self.hass.states.async_set(
                entity_id, "on", attributes={"brightness": brightness}
            )
            await self.hass.async_block_till_done()

    async def override_on(self, entity_id: str = "switch.override") -> None:
        """Simulate override switch turning on."""
        self.hass.states.async_set(entity_id, "on")
        await self.hass.async_block_till_done()

    async def override_off(self, entity_id: str = "switch.override") -> None:
        """Simulate override switch turning off."""
        self.hass.states.async_set(entity_id, "off")
        await self.hass.async_block_till_done()

    async def set_ambient_lux(self, lux: int, entity_id: str = "sensor.lux") -> None:
        """Simulate ambient light level change."""
        self.hass.states.async_set(
            entity_id,
            str(lux),
            attributes={"unit_of_measurement": "lx"},
        )
        await self.hass.async_block_till_done()

    async def set_house_active(
        self, active: bool, entity_id: str = "input_boolean.house_active"
    ) -> None:
        """Simulate house active state change."""
        self.hass.states.async_set(entity_id, "on" if active else "off")
        await self.hass.async_block_till_done()

    async def expire_timer(self, timer_name: str = "motion") -> None:
        """Simulate a timer expiring."""
        await self.coordinator._async_timer_expired(timer_name)

    async def expire_motion_delay(self) -> None:
        """Simulate the motion delay timer expiring."""
        await self.coordinator._async_motion_delay_expired("motion_delay")

    def force_state(self, state: str) -> None:
        """Force coordinator into a specific state."""
        self.coordinator.state_machine.force_state(state)

    def refresh_lights(self) -> None:
        """Refresh light controller state from HA."""
        self.coordinator.light_controller.refresh_all_states()

    def clear_event_log(self) -> None:
        """Clear the event log for targeted assertions."""
        self.coordinator._event_log.clear()


def _build_config(overrides: dict[str, Any]) -> dict[str, Any]:
    """Build a complete config dict with sensible defaults."""
    defaults = {
        CONF_MOTION_ENTITY: ["binary_sensor.motion"],
        CONF_LIGHTS: ["light.ceiling"],
        CONF_MOTION_ACTIVATION: True,
        CONF_NO_MOTION_WAIT: 300,
        CONF_EXTENDED_TIMEOUT: 1200,
        CONF_BRIGHTNESS_ACTIVE: 80,
        CONF_BRIGHTNESS_INACTIVE: 10,
    }
    defaults.update(overrides)
    return defaults


def _build_entry(data: dict[str, Any]) -> ConfigEntry:
    """Build a ConfigEntry from data."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Pipeline Test",
        data=data,
        options={},
        entry_id=f"pipeline_test_{id(data)}",
        source="user",
        unique_id=f"pipeline_test_{id(data)}",
        discovery_keys={},
    )


# -- Shared fixtures --


@pytest.fixture
async def harness(hass: HomeAssistant):
    """Create a basic harness with default config.

    Use CoordinatorHarness.create() directly for custom configs.
    """
    h = await CoordinatorHarness.create(hass)
    yield h
    await h.cleanup()


@pytest.fixture
async def multi_light_harness(hass: HomeAssistant):
    """Create a harness with multiple lights."""
    h = await CoordinatorHarness.create(
        hass,
        config_data={
            CONF_LIGHTS: ["light.ceiling", "light.lamp", "light.wall"],
        },
        initial_lights={
            "light.ceiling": {"state": "off"},
            "light.lamp": {"state": "off"},
            "light.wall": {"state": "off"},
        },
    )
    yield h
    await h.cleanup()


@pytest.fixture
async def ambient_harness(hass: HomeAssistant):
    """Create a harness with ambient light sensor."""
    h = await CoordinatorHarness.create(
        hass,
        config_data={
            CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
            CONF_AMBIENT_LIGHT_THRESHOLD: 50,
        },
        initial_ambient="100",
    )
    yield h
    await h.cleanup()


@pytest.fixture
async def override_harness(hass: HomeAssistant):
    """Create a harness with override switch."""
    h = await CoordinatorHarness.create(
        hass,
        config_data={
            CONF_OVERRIDE_SWITCH: "switch.override",
        },
    )
    yield h
    await h.cleanup()


@pytest.fixture
async def full_harness(hass: HomeAssistant):
    """Create a harness with all features: override, ambient, house_active, multi-light."""
    h = await CoordinatorHarness.create(
        hass,
        config_data={
            CONF_LIGHTS: ["light.ceiling", "light.lamp"],
            CONF_OVERRIDE_SWITCH: "switch.override",
            CONF_AMBIENT_LIGHT_SENSOR: "sensor.lux",
            CONF_AMBIENT_LIGHT_THRESHOLD: 50,
            CONF_HOUSE_ACTIVE: "input_boolean.house_active",
        },
        initial_lights={
            "light.ceiling": {"state": "off"},
            "light.lamp": {"state": "off"},
        },
    )
    yield h
    await h.cleanup()


@pytest.fixture
async def delay_harness(hass: HomeAssistant):
    """Create a harness with motion delay configured."""
    h = await CoordinatorHarness.create(
        hass,
        config_data={
            CONF_MOTION_DELAY: 5,
        },
    )
    yield h
    await h.cleanup()
