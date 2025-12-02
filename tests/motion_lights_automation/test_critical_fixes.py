"""Tests for critical bug fixes identified in deep research."""

import pytest
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from custom_components.motion_lights_automation.const import (
    CONF_MOTION_DELAY,
    CONF_MOTION_ENTITY,
    CONF_LIGHTS,
    DOMAIN,
    STATE_IDLE,
    STATE_AUTO,
    STATE_MANUAL,
    STATE_MANUAL_OFF,
    STATE_MOTION_AUTO,
    STATE_OVERRIDDEN,
)
from custom_components.motion_lights_automation.state_machine import (
    MotionLightsStateMachine,
    StateTransitionEvent,
)
from custom_components.motion_lights_automation.motion_coordinator import (
    MotionLightsCoordinator,
)


@pytest.fixture
def delay_config_entry() -> ConfigEntry:
    """Create a config entry with motion delay configured."""
    return ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Test Motion Delay",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
            CONF_MOTION_DELAY: 5,  # 5 second delay
        },
        options={},
        entry_id="test_delay",
        source="user",
        unique_id="test_delay_unique",
        discovery_keys={},
    )


class TestMotionDelayTimerCancellation:
    """Test that motion_delay timer is cancelled when motion clears during delay."""

    @pytest.mark.asyncio
    async def test_motion_delay_cancelled_on_motion_off(
        self, hass: HomeAssistant, delay_config_entry: ConfigEntry
    ):
        """Motion delay timer should be cancelled when motion clears during delay."""
        # Set up required entities
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")

        coordinator = MotionLightsCoordinator(hass, delay_config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Start in IDLE state
            assert coordinator.state_machine.current_state == STATE_IDLE

            # Simulate motion on - should start delay timer
            coordinator._handle_motion_on()

            # Verify delay timer was started
            assert coordinator.timer_manager.has_active_timer("motion_delay")

            # Motion clears during delay
            coordinator._handle_motion_off()

            # Verify delay timer was cancelled
            assert not coordinator.timer_manager.has_active_timer("motion_delay")

            # State should still be IDLE (didn't transition)
            assert coordinator.state_machine.current_state == STATE_IDLE
        finally:
            coordinator.async_cleanup_listeners()

    @pytest.mark.asyncio
    async def test_motion_delay_cancelled_on_override(
        self, hass: HomeAssistant, delay_config_entry: ConfigEntry
    ):
        """Motion delay timer should be cancelled when override activates."""
        # Set up required entities
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")

        coordinator = MotionLightsCoordinator(hass, delay_config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Start in IDLE state
            assert coordinator.state_machine.current_state == STATE_IDLE

            # Simulate motion on - should start delay timer
            coordinator._handle_motion_on()

            # Verify delay timer was started
            assert coordinator.timer_manager.has_active_timer("motion_delay")

            # Override activates during delay
            coordinator._handle_override_on()

            # Verify delay timer was cancelled
            assert not coordinator.timer_manager.has_active_timer("motion_delay")

            # State should be OVERRIDDEN
            assert coordinator.state_machine.current_state == STATE_OVERRIDDEN
        finally:
            coordinator.async_cleanup_listeners()


class TestLightsAllOffFromManual:
    """Test LIGHTS_ALL_OFF transition from MANUAL state."""

    def test_lights_all_off_from_manual_transitions_to_idle(self):
        """External automation turning off lights in MANUAL state should go to IDLE."""
        sm = MotionLightsStateMachine(initial_state=STATE_MANUAL)

        # LIGHTS_ALL_OFF should now be a valid transition from MANUAL
        result = sm.transition(StateTransitionEvent.LIGHTS_ALL_OFF)

        assert result is True
        assert sm.current_state == STATE_IDLE

    def test_manual_off_intervention_still_works(self):
        """Manual intervention (user turning off) should still go to MANUAL_OFF."""
        sm = MotionLightsStateMachine(initial_state=STATE_MANUAL)

        # MANUAL_OFF_INTERVENTION should still work
        result = sm.transition(StateTransitionEvent.MANUAL_OFF_INTERVENTION)

        assert result is True
        assert sm.current_state == STATE_MANUAL_OFF

    def test_lights_all_off_from_auto(self):
        """LIGHTS_ALL_OFF from AUTO should go to IDLE."""
        sm = MotionLightsStateMachine(initial_state=STATE_AUTO)

        result = sm.transition(StateTransitionEvent.LIGHTS_ALL_OFF)

        assert result is True
        assert sm.current_state == STATE_IDLE


@pytest.fixture
def basic_config_entry() -> ConfigEntry:
    """Create a basic config entry."""
    return ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Test Basic",
        data={
            CONF_MOTION_ENTITY: ["binary_sensor.motion"],
            CONF_LIGHTS: ["light.test"],
        },
        options={},
        entry_id="test_basic",
        source="user",
        unique_id="test_basic_unique",
        discovery_keys={},
    )


class TestTimerRaceCondition:
    """Test timer callback state validation prevents race conditions."""

    @pytest.mark.asyncio
    async def test_timer_callback_ignored_in_overridden_state(
        self, hass: HomeAssistant, basic_config_entry: ConfigEntry
    ):
        """Timer expiring in OVERRIDDEN state should not transition to IDLE."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")

        coordinator = MotionLightsCoordinator(hass, basic_config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Force to OVERRIDDEN state (simulating override activated)
            coordinator.state_machine.force_state(STATE_OVERRIDDEN)

            # Simulate timer callback firing (as if scheduled before override)
            await coordinator._async_timer_expired("motion")

            # Should still be OVERRIDDEN - timer was ignored
            assert coordinator.state_machine.current_state == STATE_OVERRIDDEN
        finally:
            coordinator.async_cleanup_listeners()

    @pytest.mark.asyncio
    async def test_timer_callback_ignored_in_motion_auto_state(
        self, hass: HomeAssistant, basic_config_entry: ConfigEntry
    ):
        """Timer expiring in MOTION_AUTO state should not transition to IDLE."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")

        coordinator = MotionLightsCoordinator(hass, basic_config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Force to MOTION_AUTO state
            coordinator.state_machine.force_state(STATE_MOTION_AUTO)

            # Simulate timer callback firing
            await coordinator._async_timer_expired("motion")

            # Should still be MOTION_AUTO - timer was ignored
            assert coordinator.state_machine.current_state == STATE_MOTION_AUTO
        finally:
            coordinator.async_cleanup_listeners()

    @pytest.mark.asyncio
    async def test_timer_callback_works_in_auto_state(
        self, hass: HomeAssistant, basic_config_entry: ConfigEntry
    ):
        """Timer expiring in AUTO state should transition to IDLE."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")

        coordinator = MotionLightsCoordinator(hass, basic_config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Force to AUTO state
            coordinator.state_machine.force_state(STATE_AUTO)

            # Simulate timer callback firing
            await coordinator._async_timer_expired("motion")

            # Should transition to IDLE
            assert coordinator.state_machine.current_state == STATE_IDLE
        finally:
            coordinator.async_cleanup_listeners()

    @pytest.mark.asyncio
    async def test_timer_callback_works_in_manual_state(
        self, hass: HomeAssistant, basic_config_entry: ConfigEntry
    ):
        """Timer expiring in MANUAL state should transition to IDLE."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")

        coordinator = MotionLightsCoordinator(hass, basic_config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Force to MANUAL state
            coordinator.state_machine.force_state(STATE_MANUAL)

            # Simulate timer callback firing
            await coordinator._async_timer_expired("extended")

            # Should transition to IDLE
            assert coordinator.state_machine.current_state == STATE_IDLE
        finally:
            coordinator.async_cleanup_listeners()

    @pytest.mark.asyncio
    async def test_timer_callback_works_in_manual_off_state(
        self, hass: HomeAssistant, basic_config_entry: ConfigEntry
    ):
        """Timer expiring in MANUAL_OFF state should transition to IDLE."""
        hass.states.async_set("binary_sensor.motion", "off")
        hass.states.async_set("light.test", "off")

        coordinator = MotionLightsCoordinator(hass, basic_config_entry)
        await coordinator.async_setup_listeners()

        try:
            # Force to MANUAL_OFF state
            coordinator.state_machine.force_state(STATE_MANUAL_OFF)

            # Simulate timer callback firing
            await coordinator._async_timer_expired("extended")

            # Should transition to IDLE
            assert coordinator.state_machine.current_state == STATE_IDLE
        finally:
            coordinator.async_cleanup_listeners()


class TestTimerCallbackPassesName:
    """Test that timer callback receives timer name."""

    @pytest.mark.asyncio
    async def test_timer_callback_receives_name(self, hass: HomeAssistant):
        """Timer callback should receive timer name as argument."""
        from custom_components.motion_lights_automation.timer_manager import (
            TimerManager,
            TimerType,
        )

        manager = TimerManager(hass)
        received_name = None

        async def callback(timer_id: str = None):
            nonlocal received_name
            received_name = timer_id

        # Start a timer with very short duration
        manager.start_timer("test_timer", TimerType.MOTION, callback, duration=0)

        # Wait for timer to fire
        await hass.async_block_till_done()

        # Give a bit more time for the callback to execute
        import asyncio

        await asyncio.sleep(0.1)
        await hass.async_block_till_done()

        # Verify callback received the timer name
        assert received_name == "test_timer"


class TestServiceRegistrationMultiEntry:
    """Test service registration handles multiple config entries correctly."""

    @pytest.mark.asyncio
    async def test_service_registered_once_check(self, hass: HomeAssistant):
        """Service should only be registered once even with multiple entries."""
        from custom_components.motion_lights_automation import (
            async_setup_entry,
            DOMAIN,
            SERVICE_REFRESH_TRACKING,
        )

        # Create first config entry
        entry1 = ConfigEntry(
            version=1,
            minor_version=0,
            domain=DOMAIN,
            title="Test Entry 1",
            data={
                CONF_MOTION_ENTITY: ["binary_sensor.motion1"],
                CONF_LIGHTS: ["light.test1"],
            },
            options={},
            entry_id="entry1",
            source="user",
            unique_id="unique1",
            discovery_keys={},
        )

        # Set up required entities
        hass.states.async_set("binary_sensor.motion1", "off")
        hass.states.async_set("light.test1", "off")

        with patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            return_value=None,
        ):
            # First entry - service should be registered
            result1 = await async_setup_entry(hass, entry1)
            assert result1 is True
            assert hass.services.has_service(DOMAIN, SERVICE_REFRESH_TRACKING)

            # Cleanup
            if hasattr(entry1, "runtime_data") and entry1.runtime_data:
                entry1.runtime_data.async_cleanup_listeners()
