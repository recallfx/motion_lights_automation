"""pytest fixtures."""

from typing import Any

import pytest
from homeassistant.core import HomeAssistant, ServiceCall


@pytest.fixture(autouse=True)
async def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in the test dir."""
    return


@pytest.fixture(autouse=True)
def auto_register_light_services(hass: HomeAssistant, request: pytest.FixtureRequest):
    """Register simple light services for coordinator tests."""
    if request.node.path.name == "test_light_controller.py":
        return

    _register_light_services(hass)


def _entity_ids(value: Any) -> list[str]:
    """Normalize Home Assistant service entity_id input."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def _register_light_services(hass: HomeAssistant) -> None:
    """Register simple light services for tests."""
    if not hass.services.has_service("light", "turn_on"):

        async def turn_on(call: ServiceCall) -> None:
            brightness_pct = call.data.get("brightness_pct", 100)
            brightness = round(max(0, min(100, int(brightness_pct))) * 255 / 100)
            attrs = {"brightness": brightness}
            for entity_id in _entity_ids(call.data.get("entity_id")):
                hass.states.async_set(entity_id, "on", attrs, context=call.context)

        hass.services.async_register("light", "turn_on", turn_on)

    if not hass.services.has_service("light", "turn_off"):

        async def turn_off(call: ServiceCall) -> None:
            for entity_id in _entity_ids(call.data.get("entity_id")):
                hass.states.async_set(entity_id, "off", context=call.context)

        hass.services.async_register("light", "turn_off", turn_off)
