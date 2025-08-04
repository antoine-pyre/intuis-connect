"""Config flow and options flow for Intuis Connect."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CannotConnect, InvalidAuth
from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_HOME_ID,
    CONF_MANUAL_DURATION,
    CONF_AWAY_DURATION,
    CONF_BOOST_DURATION,
    CONF_AWAY_TEMP,
    CONF_BOOST_TEMP,
    DEFAULT_MANUAL_DURATION,
    DEFAULT_AWAY_DURATION,
    DEFAULT_BOOST_DURATION,
    DEFAULT_AWAY_TEMP,
    DEFAULT_BOOST_TEMP,
)
from .helper import async_validate_api

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Intuis Connect."""

    VERSION = 2
    _reauth_entry: config_entries.ConfigEntry | None = None
    _username: str | None = None

    async def async_step_user(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            try:
                home_id, api = await async_validate_api(username, password, session)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            else:
                return self.async_create_entry(
                    title=f"Intuis Connect ({username})",
                    data={
                        CONF_USERNAME: username,
                        CONF_REFRESH_TOKEN: api.refresh_token,
                        CONF_HOME_ID: home_id,
                    },
                    options={
                        CONF_MANUAL_DURATION: DEFAULT_MANUAL_DURATION,
                        CONF_AWAY_DURATION: DEFAULT_AWAY_DURATION,
                        CONF_BOOST_DURATION: DEFAULT_BOOST_DURATION,
                        CONF_AWAY_TEMP: DEFAULT_AWAY_TEMP,
                        CONF_BOOST_TEMP: DEFAULT_BOOST_TEMP,
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_reauth(self, data: dict[str, Any]) -> FlowResult:
        """Handle re-authentication with Intuis Connect."""
        self._username = data[CONF_USERNAME]
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-authentication confirmation."""
        errors: dict[str, str] = {}
        if user_input is not None:
            new_password = user_input[CONF_PASSWORD]
            session = async_get_clientsession(self.hass)
            try:
                _, api = await async_validate_api(
                    self._username, new_password, session
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            else:
                assert self._reauth_entry
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        CONF_USERNAME: self._username,
                        CONF_REFRESH_TOKEN: api.refresh_token,
                        CONF_HOME_ID: self._reauth_entry.data[CONF_HOME_ID],
                    },
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

        schema = vol.Schema({vol.Required(CONF_PASSWORD): str})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"username": self._username},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
            config_entry: config_entries.ConfigEntry,
    ) -> IntuisOptionsFlow:
        """Get the options flow for this handler."""
        return IntuisOptionsFlow(config_entry)


class IntuisOptionsFlow(config_entries.OptionsFlow):
    """Handle an options flow for Intuis Connect."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry = entry

    async def async_step_init(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        def _pos_int(value: str) -> int:
            val = vol.Coerce(int)(value)
            if val <= 0:
                raise vol.Invalid("must_be_positive")
            return val

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_MANUAL_DURATION,
                    default=self._entry.options.get(
                        CONF_MANUAL_DURATION, DEFAULT_MANUAL_DURATION
                    ),
                ): _pos_int,
                vol.Optional(
                    CONF_AWAY_DURATION,
                    default=self._entry.options.get(
                        CONF_AWAY_DURATION, DEFAULT_AWAY_DURATION
                    ),
                ): _pos_int,
                vol.Optional(
                    CONF_BOOST_DURATION,
                    default=self._entry.options.get(
                        CONF_BOOST_DURATION, DEFAULT_BOOST_DURATION
                    ),
                ): _pos_int,
                vol.Optional(
                    CONF_AWAY_TEMP,
                    default=self._entry.options.get(
                        CONF_AWAY_TEMP, DEFAULT_AWAY_TEMP
                    ),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_BOOST_TEMP,
                    default=self._entry.options.get(
                        CONF_BOOST_TEMP, DEFAULT_BOOST_TEMP
                    ),
                ): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="init", data_schema=options_schema)
