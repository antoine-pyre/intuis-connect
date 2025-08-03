"""Config flow for Intuis Connect integration."""
from typing import Any, Dict
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .api import IntuisAPI, CannotConnect, InvalidAuth
from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD

class IntuisConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the configuration flow for Intuis Connect."""

    VERSION = 1

    async def async_step_user(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        errors: Dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            session = self.hass.helpers.aiohttp_client.async_get_clientsession(self.hass)
            api = IntuisAPI(session)
            try:
                await api.async_login(username, password)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(username.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"Intuis Connect ({username})", data={
                    CONF_USERNAME: username,
                    "refresh_token": api.refresh_token,
                    "home_id": api.home_id
                })
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str
            }),
            errors=errors
        )
