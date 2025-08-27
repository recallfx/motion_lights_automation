"""Config flow for the Motion lights adv integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import (
    CONF_BACKGROUND_LIGHT,
    CONF_BRIGHTNESS_DAY,
    CONF_BRIGHTNESS_NIGHT,
    CONF_CEILING_LIGHT,
    CONF_DARK_OUTSIDE,
    CONF_EXTENDED_TIMEOUT,
    CONF_FEATURE_LIGHT,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
    DEFAULT_BRIGHTNESS_DAY,
    DEFAULT_BRIGHTNESS_NIGHT,
    DEFAULT_EXTENDED_TIMEOUT,
    DEFAULT_MOTION_ACTIVATION,
    DEFAULT_NO_MOTION_WAIT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def get_user_schema(data: dict[str, Any] | None = None) -> vol.Schema:
    """Get the basic user schema with optional default values."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=data.get(CONF_NAME) if data else None): str,
            vol.Required(
                CONF_MOTION_ENTITY,
                default=data.get(CONF_MOTION_ENTITY) if data else None,
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="binary_sensor", device_class="motion"
                )
            ),
            vol.Required(
                CONF_BACKGROUND_LIGHT,
                default=data.get(CONF_BACKGROUND_LIGHT) if data else None,
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="light")),
            vol.Required(
                CONF_FEATURE_LIGHT,
                default=data.get(CONF_FEATURE_LIGHT) if data else None,
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="light")),
            vol.Required(
                CONF_CEILING_LIGHT,
                default=data.get(CONF_CEILING_LIGHT) if data else None,
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="light")),
            vol.Required(
                CONF_OVERRIDE_SWITCH,
                default=data.get(CONF_OVERRIDE_SWITCH) if data else None,
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="switch")),
            vol.Optional(
                CONF_DARK_OUTSIDE,
                default=data.get(CONF_DARK_OUTSIDE) if data else None,
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["switch", "binary_sensor"])
            ),
        }
    )


def get_advanced_schema(data: dict[str, Any] | None = None) -> vol.Schema:
    """Get the advanced options schema."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_MOTION_ACTIVATION,
                default=data.get(CONF_MOTION_ACTIVATION, DEFAULT_MOTION_ACTIVATION)
                if data
                else DEFAULT_MOTION_ACTIVATION,
            ): bool,
            vol.Optional(
                CONF_EXTENDED_TIMEOUT,
                default=data.get(CONF_EXTENDED_TIMEOUT, DEFAULT_EXTENDED_TIMEOUT)
                if data
                else DEFAULT_EXTENDED_TIMEOUT,
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=7200)),
            vol.Optional(
                CONF_NO_MOTION_WAIT,
                default=data.get(CONF_NO_MOTION_WAIT, DEFAULT_NO_MOTION_WAIT)
                if data
                else DEFAULT_NO_MOTION_WAIT,
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
            vol.Optional(
                CONF_BRIGHTNESS_DAY,
                default=data.get(CONF_BRIGHTNESS_DAY, DEFAULT_BRIGHTNESS_DAY)
                if data
                else DEFAULT_BRIGHTNESS_DAY,
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            vol.Optional(
                CONF_BRIGHTNESS_NIGHT,
                default=data.get(CONF_BRIGHTNESS_NIGHT, DEFAULT_BRIGHTNESS_NIGHT)
                if data
                else DEFAULT_BRIGHTNESS_NIGHT,
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        }
    )


STEP_USER_DATA_SCHEMA = get_user_schema()
STEP_ADVANCED_DATA_SCHEMA = get_advanced_schema()


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # Validate that all lights exist
    for key in (CONF_BACKGROUND_LIGHT, CONF_FEATURE_LIGHT, CONF_CEILING_LIGHT):
        light_ent = data.get(key)
        if not light_ent or not hass.states.get(light_ent):
            raise CannotConnect(f"Light entity {light_ent or key} not found")

    # Motion sensor is always required for determining when to turn off lights
    motion_entity = data[CONF_MOTION_ENTITY]
    if not hass.states.get(motion_entity):
        raise CannotConnect(f"Motion entity {motion_entity} not found")

    # Validate that override switch exists
    override_switch = data[CONF_OVERRIDE_SWITCH]
    if not hass.states.get(override_switch):
        raise CannotConnect(f"Override switch {override_switch} not found")

    # If dark outside entity provided, validate it exists (optional)
    dark_outside = data.get(CONF_DARK_OUTSIDE)
    if dark_outside and not hass.states.get(dark_outside):
        raise CannotConnect(f"Dark outside entity {dark_outside} not found")

    return {"title": data[CONF_NAME]}


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Motion lights adv."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._basic_config: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
                self._basic_config = user_input
                return await self.async_step_advanced()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidConfiguration:
                errors["base"] = "invalid_config"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the advanced options step."""
        if user_input is not None:
            # Merge basic and advanced config
            config_data = {**self._basic_config, **user_input}

            # Create unique ID based on motion entity and name
            unique_id = f"{config_data[CONF_MOTION_ENTITY]}_{config_data[CONF_NAME]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            # Create the config entry
            info = await validate_input(self.hass, config_data)
            return self.async_create_entry(title=info["title"], data=config_data)

        return self.async_show_form(
            step_id="advanced",
            data_schema=STEP_ADVANCED_DATA_SCHEMA,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration - basic settings."""
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        assert config_entry is not None

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
                # Store basic config and proceed to advanced
                self._basic_config = user_input
                return await self.async_step_reconfigure_advanced()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidConfiguration:
                errors["base"] = "invalid_config"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Show form with current data as defaults
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=get_user_schema(config_entry.data),
            errors=errors,
            description_placeholders={"name": config_entry.title},
        )

    async def async_step_reconfigure_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration - advanced settings."""
        config_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        assert config_entry is not None

        if user_input is not None:
            # Merge basic and advanced config
            config_data = {**self._basic_config, **user_input}

            # Check if the motion entity or name changed - if so, update unique ID
            old_unique_id = config_entry.unique_id
            new_unique_id = (
                f"{config_data[CONF_MOTION_ENTITY]}_{config_data[CONF_NAME]}"
            )

            if old_unique_id != new_unique_id:
                await self.async_set_unique_id(new_unique_id)
                self._abort_if_unique_id_mismatch(reason="wrong_account")

            return self.async_update_reload_and_abort(
                config_entry,
                data=config_data,
                reason="reconfigure_successful",
            )

        # Show advanced form with current data as defaults
        return self.async_show_form(
            step_id="reconfigure_advanced",
            data_schema=get_advanced_schema(config_entry.data),
            description_placeholders={"name": config_entry.title},
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidConfiguration(HomeAssistantError):
    """Error to indicate there is invalid configuration."""
