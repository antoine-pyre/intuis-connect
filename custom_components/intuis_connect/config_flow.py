"""Config flow and options flow for Intuis Connect."""
from __future__ import annotations
from typing import Any, Dict
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IntuisAPI, CannotConnect, InvalidAuth
from .const import (
    DOMAIN, CONF_USERNAME, CONF_PASSWORD,
    DEFAULT_MANUAL_DURATION, DEFAULT_AWAY_DURATION, DEFAULT_BOOST_DURATION,
    DEFAULT_AWAY_TEMP, DEFAULT_BOOST_TEMP,
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2
    _reauth_entry: config_entries.ConfigEntry | None = None
    _username: str | None = None

    async def async_step_user(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            api = IntuisAPI(session)
            try:
                home_id = await api.async_login(username, password)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Intuis Connect ({username})",
                    data={
                        CONF_USERNAME: username,
                        "refresh_token": api._refresh_token,
                        "home_id": home_id,
                    },
                    options={
                        "manual_duration": DEFAULT_MANUAL_DURATION,
                        "away_duration": DEFAULT_AWAY_DURATION,
                        "boost_duration": DEFAULT_BOOST_DURATION,
                        "away_temp": DEFAULT_AWAY_TEMP,
                        "boost_temp": DEFAULT_BOOST_TEMP,
                    },
                )

        data_schema = vol.Schema({
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
        })
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    async def async_step_reauth(self, data: dict[str, Any]) -> FlowResult:
        self._username = data[CONF_USERNAME]
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            new_password = user_input[CONF_PASSWORD]
            session = async_get_clientsession(self.hass)
            api = IntuisAPI(session)
            try:
                await api.async_login(self._username, new_password)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "unknown"
            else:
                assert self._reauth_entry
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        CONF_USERNAME: self._username,
                        "refresh_token": api._refresh_token,
                        "home_id": self._reauth_entry.data["home_id"],
                    },
                )
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
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
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return IntuisOptionsFlow(config_entry)


class IntuisOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry):
        self._entry = entry

    async def async_step_init(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        def _pos_int(value: str) -> int:
            val = vol.Coerce(int)(value)
            if val <= 0:
                raise vol.Invalid("must_be_positive")
            return val

        options_schema = vol.Schema({
            vol.Optional("manual_duration", default=self._entry.options.get("manual_duration", DEFAULT_MANUAL_DURATION)): _pos_int,
            vol.Optional("away_duration", default=self._entry.options.get("away_duration", DEFAULT_AWAY_DURATION)): _pos_int,
            vol.Optional("boost_duration", default=self._entry.options.get("boost_duration", DEFAULT_BOOST_DURATION)): _pos_int,
            vol.Optional("away_temp", default=self._entry.options.get("away_temp", DEFAULT_AWAY_TEMP)): vol.Coerce(float),
            vol.Optional("boost_temp", default=self._entry.options.get("boost_temp", DEFAULT_BOOST_TEMP)): vol.Coerce(float),
        })
        return self.async_show_form(step_id="init", data_schema=options_schema)
