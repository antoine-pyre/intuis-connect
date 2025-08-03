"""Config flow for Intuis Connect (Netatmo) integration."""
from __future__ import annotations

from typing import Any, Dict

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IntuisAPI, CannotConnect, InvalidAuth
from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    DEFAULT_MANUAL_DURATION,
    DEFAULT_AWAY_DURATION,
    DEFAULT_BOOST_DURATION,
    DEFAULT_AWAY_TEMP,
    DEFAULT_BOOST_TEMP,
)


class IntuisConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Intuis Connect config flow."""

    VERSION = 2
    _reauth_entry: config_entries.ConfigEntry | None = None
    _username: str | None = None

    async def async_step_user(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Step executed when the user starts the flow."""
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
                # Success – create entry
                return self.async_create_entry(
                    title=f"Intuis Connect ({username})",
                    data={
                        CONF_USERNAME: username,
                        "refresh_token": api.refresh_token,
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

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    # --- Re-authentication flow -------------------------------------------------
    async def async_step_reauth(self, data: dict[str, Any]) -> FlowResult:
        """Prepare a re-authentication flow when tokens expire or are invalid."""
        self._username = data[CONF_USERNAME]
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the credentials re-check."""
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
                # Update the existing entry with new refresh token
                assert self._reauth_entry  # mypy
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        CONF_USERNAME: self._username,
                        "refresh_token": api.refresh_token,
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

    # --- Options flow (to tweak durations / temps) ------------------------------
    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "IntuisOptionsFlow":
        """Return the options flow handler."""
        return IntuisOptionsFlow(config_entry)


class IntuisOptionsFlow(config_entries.OptionsFlow):
    """Options flow to adjust preset parameters."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Options form."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        def _positive_int(value: str) -> int:
            value_int = vol.Coerce(int)(value)
            if value_int <= 0:
                raise vol.Invalid("must_be_positive")
            return value_int

        options_schema = vol.Schema(
            {
                vol.Optional(
                    "manual_duration",
                    default=self._entry.options.get("manual_duration", DEFAULT_MANUAL_DURATION),
                ): _positive_int,
                vol.Optional(
                    "away_duration",
                    default=self._entry.options.get("away_duration", DEFAULT_AWAY_DURATION),
                ): _positive_int,
                vol.Optional(
                    "boost_duration",
                    default=self._entry.options.get("boost_duration", DEFAULT_BOOST_DURATION),
                ): _positive_int,
                vol.Optional(
                    "away_temp",
                    default=self._entry.options.get("away_temp", DEFAULT_AWAY_TEMP),
                ): vol.Coerce(float),
                vol.Optional(
                    "boost_temp",
                    default=self._entry.options.get("boost_temp", DEFAULT_BOOST_TEMP),
                ): vol.Coerce(float),
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
