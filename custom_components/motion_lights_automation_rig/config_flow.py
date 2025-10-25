"""Config flow for Motion Lights Automation Rig integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import config_validation as cv

from .const import CONF_NAME, DEFAULT_NAME, DOMAIN


class MotionLightsAutomationRigConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Motion Lights Automation Rig."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                if not user_input.get(CONF_NAME):
                    user_input[CONF_NAME] = DEFAULT_NAME

                # Set unique ID based on name to prevent duplicates
                await self.async_set_unique_id(
                    user_input[CONF_NAME].lower().replace(" ", "_")
                )
                self._abort_if_unique_id_configured()

                if not errors:
                    return self.async_create_entry(
                        title=user_input[CONF_NAME],
                        data=user_input,
                    )
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
