"""Home Assistant based simulation server.

This module runs a real Home Assistant instance with the actual
MotionLightsCoordinator, providing accurate simulation without
code duplication.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from aiohttp import web, WSMsgType

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from custom_components.motion_lights_automation.const import (
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_EXTENDED_TIMEOUT,
    CONF_LIGHTS,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
    CONF_AMBIENT_LIGHT_SENSOR,
    CONF_HOUSE_ACTIVE,
    DOMAIN,
)
from custom_components.motion_lights_automation.motion_coordinator import (
    MotionLightsCoordinator,
)
from custom_components.motion_lights_automation.state_machine import STATE_IDLE

_LOGGER = logging.getLogger(__name__)

# Default simulation configuration
DEFAULT_CONFIG = {
    CONF_MOTION_ENTITY: ["binary_sensor.sim_motion"],
    CONF_LIGHTS: ["light.sim_living_room", "light.sim_kitchen", "light.sim_bedroom"],
    CONF_OVERRIDE_SWITCH: "switch.sim_override",
    CONF_AMBIENT_LIGHT_SENSOR: "binary_sensor.sim_ambient",
    CONF_HOUSE_ACTIVE: "switch.sim_house_active",
    CONF_NO_MOTION_WAIT: 300,
    CONF_EXTENDED_TIMEOUT: 1200,
    CONF_MOTION_ACTIVATION: True,
    CONF_BRIGHTNESS_ACTIVE: 80,
    CONF_BRIGHTNESS_INACTIVE: 10,
}


class HASimulationServer:
    """Simulation server using real Home Assistant instance."""

    def __init__(self, host: str = "localhost", port: int = 8093):
        """Initialize the simulation server."""
        self.host = host
        self.port = port
        self.hass: HomeAssistant | None = None
        self.coordinator: MotionLightsCoordinator | None = None
        self.config_entry: ConfigEntry | None = None
        self._websockets: list[web.WebSocketResponse] = []
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._event_log: list[dict] = []
        self._max_log_entries = 50
        self._state_entered_at: float = time.time()

    async def start(self) -> None:
        """Start the simulation server."""
        # Initialize Home Assistant
        await self._init_hass()

        # Set up web server
        self._app = web.Application()
        self._app.router.add_get("/ws", self._websocket_handler)
        self._app.router.add_get("/", self._index_handler)
        # Serve static files at root level (js/, css/, etc.)
        static_path = Path(__file__).parent / "static"
        self._app.router.add_static("/js", static_path / "js")
        self._app.router.add_static("/static", static_path)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

        print("\n🏠 HA-Based Motion Lights Simulation Server")
        print(f"   Open http://{self.host}:{self.port} in your browser\n")

    async def stop(self) -> None:
        """Stop the simulation server."""
        # Close WebSocket connections
        for ws in self._websockets:
            await ws.close()

        # Cleanup coordinator
        if self.coordinator:
            self.coordinator.async_cleanup_listeners()

        # Stop Home Assistant
        if self.hass:
            await self.hass.async_stop()

        # Stop web server
        if self._runner:
            await self._runner.cleanup()

    async def _init_hass(self) -> None:
        """Initialize Home Assistant instance."""
        # Create Home Assistant instance
        self.hass = HomeAssistant("/tmp/ha_simulation")
        await self.hass.async_start()

        # Set up mock services
        await self._setup_mock_services()

        # Set up mock entities
        await self._setup_mock_entities()

        # Create config entry
        self.config_entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Simulation",
            data=DEFAULT_CONFIG,
            options={},
            entry_id="sim_entry",
            source="user",
            unique_id="sim_unique",
            discovery_keys={},
        )

        # Create coordinator
        self.coordinator = MotionLightsCoordinator(self.hass, self.config_entry)

        # Skip startup grace period for simulation
        self.coordinator._startup_time = dt_util.now() - __import__(
            "datetime"
        ).timedelta(seconds=200)

        # Set up listeners
        await self.coordinator.async_setup_listeners()

        # Track state changes for time_in_state calculation
        def on_state_transition(old_state, new_state, event):
            self._state_entered_at = time.time()
            # Broadcast state update
            asyncio.create_task(self._broadcast_state())

        self.coordinator.state_machine.on_transition(on_state_transition)

        # Subscribe to state changes for broadcasting
        self.hass.bus.async_listen("state_changed", self._on_state_changed)

        _LOGGER.info("Home Assistant simulation initialized")

    async def _setup_mock_services(self) -> None:
        """Register mock services for light control."""

        async def handle_light_turn_on(call):
            """Handle light.turn_on service call."""
            entity_ids = call.data.get("entity_id", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            brightness = call.data.get("brightness", 255)
            brightness_pct = call.data.get("brightness_pct")
            if brightness_pct is not None:
                brightness = int(brightness_pct * 255 / 100)

            # Preserve the context from the service call
            context = call.context

            for entity_id in entity_ids:
                if entity_id in DEFAULT_CONFIG[CONF_LIGHTS]:
                    current = self.hass.states.get(entity_id)
                    attrs = dict(current.attributes) if current else {}
                    attrs["brightness"] = brightness
                    self.hass.states.async_set(entity_id, "on", attrs, context=context)
                    _LOGGER.debug(
                        "Mock turn_on: %s brightness=%d context=%s",
                        entity_id,
                        brightness,
                        context.id if context else None,
                    )

        async def handle_light_turn_off(call):
            """Handle light.turn_off service call."""
            entity_ids = call.data.get("entity_id", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]

            # Preserve the context from the service call
            context = call.context

            for entity_id in entity_ids:
                if entity_id in DEFAULT_CONFIG[CONF_LIGHTS]:
                    current = self.hass.states.get(entity_id)
                    attrs = dict(current.attributes) if current else {}
                    attrs["brightness"] = 0
                    self.hass.states.async_set(entity_id, "off", attrs, context=context)
                    _LOGGER.debug(
                        "Mock turn_off: %s context=%s",
                        entity_id,
                        context.id if context else None,
                    )

        # Register mock light services
        self.hass.services.async_register("light", "turn_on", handle_light_turn_on)
        self.hass.services.async_register("light", "turn_off", handle_light_turn_off)

    async def _setup_mock_entities(self) -> None:
        """Set up mock entities for simulation."""
        # Motion sensor
        self.hass.states.async_set(
            "binary_sensor.sim_motion",
            "off",
            {
                "friendly_name": "Motion Sensor",
                "device_class": "motion",
            },
        )

        # Lights
        for light_id in DEFAULT_CONFIG[CONF_LIGHTS]:
            name = light_id.split(".")[-1].replace("sim_", "").replace("_", " ").title()
            self.hass.states.async_set(
                light_id,
                "off",
                {
                    "friendly_name": name,
                    "brightness": 0,
                    "supported_features": 1,  # SUPPORT_BRIGHTNESS
                },
            )

        # Override switch
        self.hass.states.async_set(
            "switch.sim_override",
            "off",
            {
                "friendly_name": "Override",
            },
        )

        # Ambient light sensor (binary - on = dark)
        self.hass.states.async_set(
            "binary_sensor.sim_ambient",
            "on",
            {
                "friendly_name": "Ambient Light",
                "device_class": "light",
            },
        )

        # House active switch
        self.hass.states.async_set(
            "switch.sim_house_active",
            "on",
            {
                "friendly_name": "House Active",
            },
        )

    @callback
    def _on_state_changed(self, event) -> None:
        """Handle state change events."""
        # Broadcast to all WebSocket clients
        asyncio.create_task(self._broadcast_state())

    async def _index_handler(self, request: web.Request) -> web.FileResponse:
        """Serve index.html."""
        return web.FileResponse(Path(__file__).parent / "static" / "index.html")

    async def _websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._websockets.append(ws)
        _LOGGER.info("WebSocket client connected (%d total)", len(self._websockets))

        # Send initial state
        await ws.send_json({"type": "init", "state": self._get_state()})

        # Register for state updates
        def on_update():
            if not ws.closed:
                asyncio.create_task(
                    ws.send_json({"type": "state_update", "state": self._get_state()})
                )

        remove_listener = (
            self.coordinator.async_add_listener(on_update)
            if self.coordinator
            else lambda: None
        )

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_message(ws, json.loads(msg.data))
                elif msg.type == WSMsgType.ERROR:
                    _LOGGER.error("WebSocket error: %s", ws.exception())
        finally:
            if callable(remove_listener):
                remove_listener()
            self._websockets.remove(ws)
            _LOGGER.info(
                "WebSocket client disconnected (%d remaining)", len(self._websockets)
            )

        return ws

    async def _handle_message(self, ws: web.WebSocketResponse, message: dict) -> None:
        """Handle incoming WebSocket message."""
        msg_type = message.get("type")
        entity_id = message.get("entity_id")
        _LOGGER.debug("Received message: %s", message)

        try:
            if msg_type == "sensor_event":
                entity_id = message.get("sensor_id") or message.get("entity_id")
                state = message.get("state", False)
                if entity_id:
                    await self._set_entity_state(entity_id, state, message)

            elif msg_type == "light_event":
                entity_id = message.get("light_id") or message.get("entity_id")
                is_on = (
                    message.get("action") == "turn_on"
                    if "action" in message
                    else message.get("state", False)
                )
                brightness = message.get("brightness", 80 if is_on else 0)
                # Convert percentage to 0-255 if needed
                if brightness <= 100:
                    brightness = int(brightness * 255 / 100)
                if entity_id:
                    await self._set_light_state(entity_id, is_on, brightness)

            elif msg_type == "config_change":
                key = message.get("key")
                value = message.get("value")
                await self._set_config(key, value)

            elif msg_type == "reset":
                await self._reset_simulation()

            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

            # Legacy action-based messages
            elif message.get("action") == "set_state":
                state = message.get("state")
                await self._set_entity_state(entity_id, state, message)

            elif message.get("action") == "turn_on":
                brightness = message.get("brightness", 255)
                await self._set_light_state(entity_id, True, brightness)

            elif message.get("action") == "turn_off":
                await self._set_light_state(entity_id, False, 0)

            elif message.get("action") == "set_brightness":
                brightness = message.get("brightness", 255)
                await self._set_light_state(entity_id, True, brightness)

            elif message.get("action") == "set_config":
                key = message.get("key")
                value = message.get("value")
                await self._set_config(key, value)

            elif message.get("action") == "reset":
                await self._reset_simulation()

            elif message.get("action") == "get_state":
                await ws.send_json({"type": "state_update", "state": self._get_state()})

        except Exception as e:
            _LOGGER.exception("Error handling message: %s", e)
            await ws.send_json({"error": str(e)})

        # Broadcast updated state
        await self._broadcast_state()

    async def _set_entity_state(
        self, entity_id: str, state: bool, message: dict
    ) -> None:
        """Set entity state."""
        if entity_id.startswith("binary_sensor.") or entity_id.startswith("switch."):
            state_str = "on" if state else "off"
            current = self.hass.states.get(entity_id)
            attrs = current.attributes if current else {}
            self.hass.states.async_set(entity_id, state_str, attrs)
            self._log_event(
                f"{entity_id.split('.')[-1]}: {state_str.upper()}", "sensor"
            )

    async def _set_light_state(
        self, entity_id: str, is_on: bool, brightness: int
    ) -> None:
        """Set light state with brightness."""
        state_str = "on" if is_on else "off"
        current = self.hass.states.get(entity_id)
        attrs = dict(current.attributes) if current else {}
        attrs["brightness"] = brightness if is_on else 0

        self.hass.states.async_set(entity_id, state_str, attrs)
        self._log_event(
            f"{entity_id.split('.')[-1]}: {state_str.upper()} (manual)", "light"
        )

    async def _set_config(self, key: str, value: Any) -> None:
        """Set configuration value."""
        if key == "is_house_active":
            self.hass.states.async_set(
                "switch.sim_house_active",
                "on" if value else "off",
                {"friendly_name": "House Active"},
            )
            self._log_event(f"House active: {value}", "config")

        elif key == "is_dark_inside":
            # Binary sensor: on = dark
            self.hass.states.async_set(
                "binary_sensor.sim_ambient",
                "on" if value else "off",
                {"friendly_name": "Ambient Light", "device_class": "light"},
            )
            self._log_event(f"Dark inside: {value}", "config")

        elif key == "motion_activation":
            if self.coordinator:
                self.coordinator.motion_activation = value
                self._log_event(f"Motion activation: {value}", "config")

    async def _reset_simulation(self) -> None:
        """Reset simulation to initial state."""
        # Turn off all lights
        for light_id in DEFAULT_CONFIG[CONF_LIGHTS]:
            self.hass.states.async_set(light_id, "off", {"brightness": 0})

        # Reset sensors
        self.hass.states.async_set("binary_sensor.sim_motion", "off")
        self.hass.states.async_set("switch.sim_override", "off")
        self.hass.states.async_set("binary_sensor.sim_ambient", "on")
        self.hass.states.async_set("switch.sim_house_active", "on")

        # Reset coordinator state
        if self.coordinator:
            self.coordinator.timer_manager.cancel_all_timers()
            self.coordinator.state_machine.force_state(STATE_IDLE)

        self._state_entered_at = time.time()
        self._event_log.clear()
        self._log_event("Simulation reset", "system")

    def _get_state(self) -> dict[str, Any]:
        """Get current simulation state."""
        if not self.hass or not self.coordinator:
            return {"error": "Not initialized"}

        # Get light states
        lights = {}
        for light_id in DEFAULT_CONFIG[CONF_LIGHTS]:
            state = self.hass.states.get(light_id)
            if state:
                brightness = state.attributes.get("brightness", 0) or 0
                lights[light_id] = {
                    "entity_id": light_id,
                    "is_on": state.state == "on",
                    "brightness_pct": int(brightness * 100 / 255) if brightness else 0,
                }

        # Get sensor states
        sensors = {}
        motion_state = self.hass.states.get("binary_sensor.sim_motion")
        if motion_state:
            sensors["binary_sensor.sim_motion"] = {
                "entity_id": "binary_sensor.sim_motion",
                "state": motion_state.state == "on",
                "type": "motion",
            }

        override_state = self.hass.states.get("switch.sim_override")
        if override_state:
            sensors["switch.sim_override"] = {
                "entity_id": "switch.sim_override",
                "state": override_state.state == "on",
                "type": "override",
            }

        # Get timer info
        timers = {}
        for timer in self.coordinator.timer_manager.get_active_timers():
            timers[timer.name] = {
                "name": timer.name,
                "type": timer.timer_type.value,
                "duration": timer.duration,
                "remaining": timer.remaining_seconds,  # UI expects 'remaining'
                "remaining_seconds": timer.remaining_seconds,
                "active": timer.is_active,  # UI expects 'active'
                "is_active": timer.is_active,
            }

        # Get ambient/house active
        ambient_state = self.hass.states.get("binary_sensor.sim_ambient")
        house_state = self.hass.states.get("switch.sim_house_active")

        return {
            "current_state": self.coordinator.current_state,
            "previous_state": self.coordinator.state_machine.previous_state,
            "time_in_state": int(time.time() - self._state_entered_at),
            "lights": lights,
            "sensors": sensors,
            "timers": timers,
            "override_active": override_state.state == "on"
            if override_state
            else False,
            "config": {
                "motion_activation": self.coordinator.motion_activation,
                "is_house_active": house_state.state == "on" if house_state else True,
                "is_dark_inside": ambient_state.state == "on"
                if ambient_state
                else True,
                "no_motion_wait": self.coordinator._no_motion_wait,
                "extended_timeout": self.coordinator.extended_timeout,
                "brightness_active": self.coordinator.brightness_active,
                "brightness_inactive": self.coordinator.brightness_inactive,
            },
            "event_log": list(self._event_log),
            "timestamp": time.time(),
        }

    async def _broadcast_state(self) -> None:
        """Broadcast state to all WebSocket clients."""
        message = {"type": "state_update", "state": self._get_state()}
        for ws in self._websockets:
            try:
                await ws.send_json(message)
            except Exception as e:
                _LOGGER.error("Error broadcasting to client: %s", e)

    def _log_event(self, message: str, event_type: str = "info") -> None:
        """Log an event."""
        from datetime import datetime

        entry = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "type": event_type,
        }
        self._event_log.append(entry)
        if len(self._event_log) > self._max_log_entries:
            self._event_log.pop(0)
        _LOGGER.info(message)


async def run_ha_simulation():
    """Run the HA-based simulation server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    server = HASimulationServer()
    await server.start()

    try:
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await server.stop()


def run_server():
    """Entry point for the HA simulation server."""
    asyncio.run(run_ha_simulation())


if __name__ == "__main__":
    run_server()
