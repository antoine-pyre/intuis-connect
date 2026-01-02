"""Config flow and options flow for Intuis Connect."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .intuis_api.api import CannotConnect, InvalidAuth
from .utils.const import (
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
    CONF_INDEFINITE_MODE,
    CONF_ENERGY_SCALE,
    CONF_IMPORT_HISTORY,
    CONF_HISTORY_DAYS,
    DEFAULT_MANUAL_DURATION,
    DEFAULT_AWAY_DURATION,
    DEFAULT_BOOST_DURATION,
    DEFAULT_AWAY_TEMP,
    DEFAULT_BOOST_TEMP,
    DEFAULT_INDEFINITE_MODE,
    DEFAULT_ENERGY_SCALE,
    DEFAULT_IMPORT_HISTORY,
    DEFAULT_HISTORY_DAYS,
    ENERGY_SCALE_OPTIONS,
    HISTORY_DAYS_OPTIONS,
    DURATION_OPTIONS_SHORT,
    DURATION_OPTIONS_LONG,
)
from .utils.helper import async_validate_api

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Intuis Connect."""

    VERSION = 2
    _reauth_entry: config_entries.ConfigEntry | None = None
    _username: str | None = None
    _home_id: str | None = None
    _refresh_token: str | None = None
    _override_options: dict[str, Any] = {}

    async def async_step_user(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Handle credentials."""
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
                self._username = username
                self._home_id = home_id
                self._refresh_token = api.refresh_token
                return await self.async_step_indefinite()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.EMAIL)
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_indefinite(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Configure indefinite override mode."""
        if user_input is not None:
            self._override_options[CONF_INDEFINITE_MODE] = user_input.get(
                CONF_INDEFINITE_MODE, DEFAULT_INDEFINITE_MODE
            )
            return await self.async_step_overrides()

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_INDEFINITE_MODE,
                    default=DEFAULT_INDEFINITE_MODE,
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="indefinite",
            data_schema=options_schema,
            description_placeholders={},
        )

    async def async_step_overrides(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Configure override durations and temperatures."""
        if user_input is not None:
            # Convert duration strings back to integers for storage
            user_input[CONF_MANUAL_DURATION] = int(user_input[CONF_MANUAL_DURATION])
            user_input[CONF_AWAY_DURATION] = int(user_input[CONF_AWAY_DURATION])
            user_input[CONF_BOOST_DURATION] = int(user_input[CONF_BOOST_DURATION])
            self._override_options.update(user_input)
            return await self.async_step_energy()

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_AWAY_TEMP,
                    default=DEFAULT_AWAY_TEMP,
                ): NumberSelector(
                    NumberSelectorConfig(min=5.0, max=30.0, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_BOOST_TEMP,
                    default=DEFAULT_BOOST_TEMP,
                ): NumberSelector(
                    NumberSelectorConfig(min=5.0, max=30.0, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_MANUAL_DURATION,
                    default=str(DEFAULT_MANUAL_DURATION),
                ): SelectSelector(
                    SelectSelectorConfig(options=DURATION_OPTIONS_SHORT, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Optional(
                    CONF_AWAY_DURATION,
                    default=str(DEFAULT_AWAY_DURATION),
                ): SelectSelector(
                    SelectSelectorConfig(options=DURATION_OPTIONS_LONG, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Optional(
                    CONF_BOOST_DURATION,
                    default=str(DEFAULT_BOOST_DURATION),
                ): SelectSelector(
                    SelectSelectorConfig(options=DURATION_OPTIONS_SHORT, mode=SelectSelectorMode.DROPDOWN)
                ),
            }
        )
        return self.async_show_form(
            step_id="overrides",
            data_schema=options_schema,
        )

    async def async_step_energy(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Configure energy settings and history import."""
        if user_input is not None:
            # Combine all options
            all_options = {
                **self._override_options,
                CONF_ENERGY_SCALE: user_input.get(CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE),
                CONF_IMPORT_HISTORY: user_input.get(CONF_IMPORT_HISTORY, DEFAULT_IMPORT_HISTORY),
                CONF_HISTORY_DAYS: int(user_input.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)),
            }

            return self.async_create_entry(
                title=f"Intuis Connect ({self._username})",
                data={
                    CONF_USERNAME: self._username,
                    CONF_REFRESH_TOKEN: self._refresh_token,
                    CONF_HOME_ID: self._home_id,
                },
                options=all_options,
            )

        # Build select options for energy scale
        energy_options = [
            {"value": key, "label": label}
            for key, label in ENERGY_SCALE_OPTIONS.items()
        ]
        # Build select options for history days
        history_options = [
            {"value": key, "label": label}
            for key, label in HISTORY_DAYS_OPTIONS.items()
        ]

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENERGY_SCALE,
                    default=DEFAULT_ENERGY_SCALE,
                ): SelectSelector(
                    SelectSelectorConfig(options=energy_options, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Optional(
                    CONF_IMPORT_HISTORY,
                    default=DEFAULT_IMPORT_HISTORY,
                ): BooleanSelector(),
                vol.Optional(
                    CONF_HISTORY_DAYS,
                    default=str(DEFAULT_HISTORY_DAYS),
                ): SelectSelector(
                    SelectSelectorConfig(options=history_options, mode=SelectSelectorMode.DROPDOWN)
                ),
            }
        )
        return self.async_show_form(
            step_id="energy",
            data_schema=options_schema,
        )

    async def async_step_reauth(self, data: dict[str, Any]) -> FlowResult:
        """Handle re-authentication with Intuis Connect."""
        self._username = data[CONF_USERNAME]
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

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
        self._override_options: dict[str, Any] = {}

    async def async_step_init(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Start with indefinite mode configuration."""
        return await self.async_step_indefinite()

    async def async_step_indefinite(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Configure indefinite override mode."""
        if user_input is not None:
            self._override_options[CONF_INDEFINITE_MODE] = user_input.get(
                CONF_INDEFINITE_MODE, DEFAULT_INDEFINITE_MODE
            )
            return await self.async_step_overrides()

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_INDEFINITE_MODE,
                    default=self._entry.options.get(
                        CONF_INDEFINITE_MODE, DEFAULT_INDEFINITE_MODE
                    ),
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="indefinite",
            data_schema=options_schema,
            description_placeholders={},
        )

    async def async_step_overrides(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Configure override durations and temperatures."""
        if user_input is not None:
            # Convert duration strings back to integers for storage
            user_input[CONF_MANUAL_DURATION] = int(user_input[CONF_MANUAL_DURATION])
            user_input[CONF_AWAY_DURATION] = int(user_input[CONF_AWAY_DURATION])
            user_input[CONF_BOOST_DURATION] = int(user_input[CONF_BOOST_DURATION])
            self._override_options.update(user_input)
            return await self.async_step_energy()

        # Get current values (convert to string for dropdown)
        manual_duration = str(self._entry.options.get(CONF_MANUAL_DURATION, DEFAULT_MANUAL_DURATION))
        away_duration = str(self._entry.options.get(CONF_AWAY_DURATION, DEFAULT_AWAY_DURATION))
        boost_duration = str(self._entry.options.get(CONF_BOOST_DURATION, DEFAULT_BOOST_DURATION))

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_AWAY_TEMP,
                    default=self._entry.options.get(
                        CONF_AWAY_TEMP, DEFAULT_AWAY_TEMP
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(min=5.0, max=30.0, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_BOOST_TEMP,
                    default=self._entry.options.get(
                        CONF_BOOST_TEMP, DEFAULT_BOOST_TEMP
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(min=5.0, max=30.0, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement="°C")
                ),
                vol.Optional(
                    CONF_MANUAL_DURATION,
                    default=manual_duration,
                ): SelectSelector(
                    SelectSelectorConfig(options=DURATION_OPTIONS_SHORT, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Optional(
                    CONF_AWAY_DURATION,
                    default=away_duration,
                ): SelectSelector(
                    SelectSelectorConfig(options=DURATION_OPTIONS_LONG, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Optional(
                    CONF_BOOST_DURATION,
                    default=boost_duration,
                ): SelectSelector(
                    SelectSelectorConfig(options=DURATION_OPTIONS_SHORT, mode=SelectSelectorMode.DROPDOWN)
                ),
            }
        )
        return self.async_show_form(
            step_id="overrides",
            data_schema=options_schema,
        )

    async def async_step_energy(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Configure energy settings."""
        if user_input is not None:
            # Combine all options
            all_options = {
                **self._override_options,
                CONF_ENERGY_SCALE: user_input.get(CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE),
            }
            return self.async_create_entry(title="", data=all_options)

        # Build select options for energy scale
        energy_options = [
            {"value": key, "label": label}
            for key, label in ENERGY_SCALE_OPTIONS.items()
        ]

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENERGY_SCALE,
                    default=self._entry.options.get(
                        CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(options=energy_options, mode=SelectSelectorMode.DROPDOWN)
                ),
            }
        )
        return self.async_show_form(
            step_id="energy",
            data_schema=options_schema,
        )
