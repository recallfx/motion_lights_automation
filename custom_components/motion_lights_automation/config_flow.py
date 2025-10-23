"""Config flow for the Motion lights automation integration."""

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
    CONF_BRIGHTNESS_ACTIVE,
    CONF_BRIGHTNESS_INACTIVE,
    CONF_CEILING_LIGHT,
    CONF_DARK_OUTSIDE,
    CONF_EXTENDED_TIMEOUT,
    CONF_FEATURE_LIGHT,
    CONF_HOUSE_ACTIVE,
    CONF_MOTION_ACTIVATION,
    CONF_MOTION_ENTITY,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_SWITCH,
    DEFAULT_BRIGHTNESS_ACTIVE,
    DEFAULT_BRIGHTNESS_INACTIVE,
    DEFAULT_EXTENDED_TIMEOUT,
    DEFAULT_MOTION_ACTIVATION,
    DEFAULT_NO_MOTION_WAIT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def get_user_schema(data: dict[str, Any] | None = None) -> vol.Schema:
    """Get the basic user schema with optional default values.

    All fields are optional. Motion and light selectors support multiple entities.
    Defaults for multi-select fields are empty lists to avoid type errors when omitted.
    """

    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(v) for v in value]
        return []

    motion_default = _as_list(data.get(CONF_MOTION_ENTITY)) if data else []
    bg_default = _as_list(data.get(CONF_BACKGROUND_LIGHT)) if data else []
    feat_default = _as_list(data.get(CONF_FEATURE_LIGHT)) if data else []
    ceil_default = _as_list(data.get(CONF_CEILING_LIGHT)) if data else []

    # For optional single-entity selectors, only set default if data exists AND has a value
    schema_dict = {
        vol.Optional(
            CONF_NAME, default=(data.get(CONF_NAME) if data else None)
        ): str,
        vol.Optional(
            CONF_MOTION_ENTITY,
            default=motion_default,
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="binary_sensor",
                device_class="motion",
                multiple=True,
            )
        ),
        vol.Optional(
            CONF_BACKGROUND_LIGHT,
            default=bg_default,
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="light", multiple=True)
        ),
        vol.Optional(
            CONF_FEATURE_LIGHT,
            default=feat_default,
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="light", multiple=True)
        ),
        vol.Optional(
            CONF_CEILING_LIGHT,
            default=ceil_default,
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="light", multiple=True)
        ),
    }

    # Only add defaults for optional single-entity selectors if they have values
    if data and data.get(CONF_OVERRIDE_SWITCH):
        schema_dict[vol.Optional(CONF_OVERRIDE_SWITCH, default=data.get(CONF_OVERRIDE_SWITCH))] = \
            selector.EntitySelector(selector.EntitySelectorConfig(domain="switch"))
    else:
        schema_dict[vol.Optional(CONF_OVERRIDE_SWITCH)] = \
            selector.EntitySelector(selector.EntitySelectorConfig(domain="switch"))

    if data and data.get(CONF_DARK_OUTSIDE):
        schema_dict[vol.Optional(CONF_DARK_OUTSIDE, default=data.get(CONF_DARK_OUTSIDE))] = \
            selector.EntitySelector(selector.EntitySelectorConfig(domain=["switch", "binary_sensor"]))
    else:
        schema_dict[vol.Optional(CONF_DARK_OUTSIDE)] = \
            selector.EntitySelector(selector.EntitySelectorConfig(domain=["switch", "binary_sensor"]))

    if data and data.get(CONF_HOUSE_ACTIVE):
        schema_dict[vol.Optional(CONF_HOUSE_ACTIVE, default=data.get(CONF_HOUSE_ACTIVE))] = \
            selector.EntitySelector(selector.EntitySelectorConfig(domain=["input_boolean", "switch", "binary_sensor"]))
    else:
        schema_dict[vol.Optional(CONF_HOUSE_ACTIVE)] = \
            selector.EntitySelector(selector.EntitySelectorConfig(domain=["input_boolean", "switch", "binary_sensor"]))

    return vol.Schema(schema_dict)


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
                CONF_BRIGHTNESS_ACTIVE,
                default=data.get(CONF_BRIGHTNESS_ACTIVE, DEFAULT_BRIGHTNESS_ACTIVE)
                if data
                else DEFAULT_BRIGHTNESS_ACTIVE,
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            vol.Optional(
                CONF_BRIGHTNESS_INACTIVE,
                default=data.get(CONF_BRIGHTNESS_INACTIVE, DEFAULT_BRIGHTNESS_INACTIVE)
                if data
                else DEFAULT_BRIGHTNESS_INACTIVE,
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        }
    )


STEP_USER_DATA_SCHEMA = get_user_schema()
STEP_ADVANCED_DATA_SCHEMA = get_advanced_schema()


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """

    # Helper to normalize a config value into a list of entity_ids
    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(v) for v in value]
        return []

    # Validate provided lights (optional; only validate if user set them)
    for key in (CONF_BACKGROUND_LIGHT, CONF_FEATURE_LIGHT, CONF_CEILING_LIGHT):
        for ent in _as_list(data.get(key)):
            if not hass.states.get(ent):
                raise CannotConnect(f"Light entity {ent} not found")

    # Validate provided motion sensors (optional)
    for ent in _as_list(data.get(CONF_MOTION_ENTITY)):
        if not hass.states.get(ent):
            raise CannotConnect(f"Motion entity {ent} not found")

    # Validate override switch if provided (accept single or list defensively)
    override_val = data.get(CONF_OVERRIDE_SWITCH)
    for ov in _as_list(override_val):
        if not hass.states.get(ov):
            raise CannotConnect(f"Override switch {ov} not found")

    # If dark outside entity provided, validate it exists (optional)
    dark_outside = data.get(CONF_DARK_OUTSIDE)
    if dark_outside and not hass.states.get(dark_outside):
        raise CannotConnect(f"Dark outside entity {dark_outside} not found")

    # If house active entity provided, validate it exists (optional)
    house_active = data.get(CONF_HOUSE_ACTIVE)
    if house_active and not hass.states.get(house_active):
        raise CannotConnect(f"House active entity {house_active} not found")

    return {"title": data.get(CONF_NAME) or "Motion lights automation"}


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Motion lights automation."""

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
            def _normalize_list(val: Any) -> list[str]:
                if val is None:
                    return []
                if isinstance(val, str):
                    return [val]
                if isinstance(val, (list, tuple, set)):
                    return [str(v) for v in val]
                return []

            motion_list = sorted(_normalize_list(config_data.get(CONF_MOTION_ENTITY)))
            name = config_data.get(CONF_NAME) or DOMAIN
            motion_key = "|".join(motion_list) if motion_list else "no-motion"
            unique_id = f"{name}:{motion_key}"
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

            def _normalize_list(val: Any) -> list[str]:
                if val is None:
                    return []
                if isinstance(val, str):
                    return [val]
                if isinstance(val, (list, tuple, set)):
                    return [str(v) for v in val]
                return []

            motion_list = sorted(_normalize_list(config_data.get(CONF_MOTION_ENTITY)))
            name = config_data.get(CONF_NAME) or DOMAIN
            motion_key = "|".join(motion_list) if motion_list else "no-motion"
            new_unique_id = f"{name}:{motion_key}"

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
