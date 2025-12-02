"""Web server for motion lights simulation.

Provides HTTP and WebSocket endpoints for the simulation UI.
Uses aiohttp for async handling.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from aiohttp import web, WSMsgType

from .sim_coordinator import SimConfig, SimMotionCoordinator


def get_default_config() -> SimConfig:
    """Return default simulation config."""
    return SimConfig(
        lights=["light.living_room", "light.kitchen", "light.bedroom"],
        motion_sensors=[
            "binary_sensor.motion_living_room",
            "binary_sensor.motion_kitchen",
            "binary_sensor.motion_bedroom",
        ],
        override_switch="switch.override",
        no_motion_wait=30,  # Short for testing
        extended_timeout=60,  # Short for testing
    )


_LOGGER = logging.getLogger(__name__)

# Global state
coordinator: SimMotionCoordinator | None = None
clients: set[web.WebSocketResponse] = set()


class WebSocketLogHandler(logging.Handler):
    """Log handler that broadcasts to WebSocket clients."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.INFO:
            return

        message = {
            "type": "log",
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        # Schedule broadcast (can't await in emit)
        for ws in list(clients):
            if not ws.closed:
                asyncio.create_task(ws.send_json(message))


async def broadcast_state() -> None:
    """Broadcast current state to all connected clients."""
    if not coordinator:
        return

    state = coordinator.get_simulation_state()
    message = {"type": "state_update", "state": state}

    for ws in list(clients):
        if not ws.closed:
            try:
                await ws.send_json(message)
            except Exception as err:
                _LOGGER.warning("Error broadcasting to client: %s", err)
                clients.discard(ws)


async def index_handler(request: web.Request) -> web.FileResponse:
    """Serve index.html."""
    static_dir = Path(__file__).parent / "static"
    return web.FileResponse(static_dir / "index.html")


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket connections."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)

    _LOGGER.info("WebSocket client connected (%d total)", len(clients))

    # Send initial state
    await ws.send_json(
        {
            "type": "init",
            "state": coordinator.get_simulation_state() if coordinator else {},
        }
    )

    # Register for state updates
    def on_update():
        if not ws.closed:
            asyncio.create_task(
                ws.send_json(
                    {
                        "type": "state_update",
                        "state": coordinator.get_simulation_state(),
                    }
                )
            )

    remove_listener = (
        coordinator.async_add_listener(on_update) if coordinator else lambda: None
    )

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await handle_ws_message(ws, data)
                except json.JSONDecodeError:
                    _LOGGER.warning("Invalid JSON from client")
            elif msg.type == WSMsgType.ERROR:
                _LOGGER.error("WebSocket error: %s", ws.exception())
    finally:
        remove_listener()
        clients.discard(ws)
        _LOGGER.info("WebSocket client disconnected (%d remaining)", len(clients))

    return ws


async def handle_ws_message(ws: web.WebSocketResponse, data: dict[str, Any]) -> None:
    """Handle incoming WebSocket message."""
    msg_type = data.get("type")

    if msg_type == "sensor_event":
        entity_id = data.get("sensor_id") or data.get("entity_id")
        state = data.get("state", False)
        if entity_id and coordinator:
            await coordinator.process_sensor_event(entity_id, state)

    elif msg_type == "light_event":
        entity_id = data.get("light_id") or data.get("entity_id")
        is_on = (
            data.get("action") == "turn_on"
            if "action" in data
            else data.get("state", False)
        )
        brightness = data.get("brightness", 80 if is_on else 0)
        if entity_id and coordinator:
            await coordinator.process_light_event(entity_id, is_on, brightness)

    elif msg_type == "config_change":
        key = data.get("key")
        value = data.get("value")
        if coordinator:
            if key == "is_house_active":
                coordinator.set_house_active(value)
            elif key == "is_dark_inside":
                coordinator.set_dark_inside(value)
            elif key == "motion_activation":
                coordinator.set_motion_activation(value)

    elif msg_type == "reset":
        if coordinator:
            coordinator.reset()

    elif msg_type == "ping":
        await ws.send_json({"type": "pong"})


async def api_history(request: web.Request) -> web.Response:
    """Return simulation history."""
    if not coordinator:
        return web.json_response({"error": "No coordinator"}, status=500)

    return web.json_response(
        {
            "history": coordinator.get_history(),
        }
    )


async def api_state(request: web.Request) -> web.Response:
    """Return current state."""
    if not coordinator:
        return web.json_response({"error": "No coordinator"}, status=500)

    return web.json_response(coordinator.get_simulation_state())


async def api_reset(request: web.Request) -> web.Response:
    """Reset simulation."""
    if coordinator:
        coordinator.reset()
    return web.json_response({"status": "ok"})


def create_app(config: SimConfig | None = None) -> web.Application:
    """Create the aiohttp application."""
    global coordinator

    # Initialize coordinator
    config = config or get_default_config()
    coordinator = SimMotionCoordinator(config)

    # Set up logging handler
    log_handler = WebSocketLogHandler()
    log_handler.setLevel(logging.INFO)
    logging.getLogger("simulation").addHandler(log_handler)

    # Create app
    app = web.Application()

    # Routes
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/api/history", api_history)
    app.router.add_get("/api/state", api_state)
    app.router.add_post("/api/reset", api_reset)

    # Static files
    static_dir = Path(__file__).parent / "static"
    app.router.add_static("/static", static_dir)
    app.router.add_static("/js", static_dir / "js")

    return app


def run_server(
    host: str = "0.0.0.0", port: int = 8092, config: SimConfig | None = None
) -> None:
    """Run the simulation server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = create_app(config)

    print("\n🏠 Motion Lights Simulation Server")
    print(f"   Open http://localhost:{port} in your browser\n")

    web.run_app(app, host=host, port=port, print=None)


if __name__ == "__main__":
    run_server()
