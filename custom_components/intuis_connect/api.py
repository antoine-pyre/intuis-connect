"""API client for Intuis Connect (Muller Intuitiv with Netatmo)."""
import asyncio
import logging
from typing import Any, Dict, Optional

import aiohttp

from .const import (
    AUTH_URL, API_GET_HOMESDATA, API_GET_HOME_STATUS, API_SET_STATE,
    CLIENT_ID, CLIENT_SECRET, AUTH_SCOPE, USER_PREFIX,
    APP_TYPE, APP_VERSION
)

LOGGER = logging.getLogger(__name__)

class IntuisAPI:
    """Class to interact with the Intuis Connect API."""

    def __init__(self, session: aiohttp.ClientSession, home_id: Optional[str] = None):
        self._session = session
        self.home_id: Optional[str] = home_id
        self.home_timezone: Optional[str] = None
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expiry: Optional[float] = None  # epoch time when token expires

    @property
    def refresh_token(self) -> Optional[str]:
        """Return the current refresh token."""
        return self._refresh_token

    def set_tokens(self, access_token: str, refresh_token: str, expires_in: int):
        """Store tokens and expiration."""
        self._access_token = access_token
        self._refresh_token = refresh_token
        if expires_in:
            self._token_expiry = asyncio.get_running_loop().time() + expires_in
        else:
            self._token_expiry = None

    async def async_login(self, username: str, password: str) -> str:
        """Authenticate with user credentials and retrieve home ID."""
        payload = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": AUTH_SCOPE,
            "user_prefix": USER_PREFIX,
            "app_version": APP_VERSION
        }
        try:
            async with self._session.post(AUTH_URL, data=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    LOGGER.error("Login failed, status %d: %s", resp.status, text)
                    if resp.status in (400, 401):
                        raise InvalidAuth("Invalid credentials")
                    raise CannotConnect(f"HTTP {resp.status}")
                data = await resp.json()
        except asyncio.TimeoutError as err:
            raise CannotConnect("Timeout") from err
        except aiohttp.ClientError as err:
            raise CannotConnect("Connection error") from err

        if "access_token" not in data:
            err_desc = data.get("error_description") or data.get("error")
            raise InvalidAuth(err_desc or "Invalid credentials")
        self.set_tokens(data["access_token"], data.get("refresh_token"), data.get("expires_in") or 0)
        await self.async_get_homes_data()
        if not self.home_id:
            raise InvalidAuth("No home available")
        return self.home_id

    async def async_refresh_access_token(self) -> bool:
        """Refresh the OAuth2 access token."""
        if not self._refresh_token:
            raise InvalidAuth("No refresh token")
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "user_prefix": USER_PREFIX
        }
        async with self._session.post(AUTH_URL, data=payload) as resp:
            if resp.status != 200:
                raise InvalidAuth("Refresh failed")
            data = await resp.json()
        self.set_tokens(data["access_token"], data.get("refresh_token", self._refresh_token),
                        data.get("expires_in") or 0)
        return True

    async def async_get_homes_data(self) -> Dict[str, Any]:
        """Retrieve home configuration data."""
        await self._ensure_token()
        headers = {"Authorization": f"Bearer {self._access_token}"}
        async with self._session.get(API_GET_HOMESDATA, headers=headers) as resp:
            if resp.status == 401:
                await self.async_refresh_access_token()
                headers["Authorization"] = f"Bearer {self._access_token}"
                resp = await self._session.get(API_GET_HOMESDATA, headers=headers)
            if resp.status != 200:
                raise APIError("homesdata failed")
            data = await resp.json()
        home = data.get("body", {}).get("homes", [])[0]
        self.home_id = home.get("id")
        self.home_timezone = home.get("timezone", "GMT")
        return home

    async def async_get_home_status(self) -> Dict[str, Any]:
        """Retrieve dynamic status info."""
        await self._ensure_token()
        headers = {"Authorization": f"Bearer {self._access_token}"}
        payload = {"home_id": self.home_id}
        async with self._session.post(API_GET_HOME_STATUS, headers=headers, data=payload) as resp:
            if resp.status == 401:
                await self.async_refresh_access_token()
                headers["Authorization"] = f"Bearer {self._access_token}"
                resp = await self._session.post(API_GET_HOME_STATUS, headers=headers, data=payload)
            if resp.status != 200:
                raise APIError("homestatus failed")
            return await resp.json()

    async def async_set_room_state(self, room_id: str, mode: str, temp: Optional[float] = None, duration: Optional[int] = None):
        """Send a command to set the room state."""
        await self._ensure_token()
        import time
        room_payload: Dict[str, Any] = {"id": room_id, "therm_setpoint_mode": mode}
        if mode == "manual":
            if temp is None:
                raise APIError("Manual mode requires temperature")
            end_time = int(time.time()) + (duration or 120) * 60
            room_payload.update({
                "therm_setpoint_temperature": float(temp),
                "therm_setpoint_end_time": end_time
            })
        payload = {
            "app_type": APP_TYPE,
            "app_version": APP_VERSION,
            "home": {
                "id": self.home_id,
                "rooms": [room_payload],
                "timezone": self.home_timezone or "GMT"
            }
        }
        headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}
        async with self._session.post(API_SET_STATE, headers=headers, json=payload) as resp:
            if resp.status == 401:
                await self.async_refresh_access_token()
                headers["Authorization"] = f"Bearer {self._access_token}"
                resp = await self._session.post(API_SET_STATE, headers=headers, json=payload)
            if resp.status != 200:
                raise APIError("setstate failed")
            return await resp.json()

    async def _ensure_token(self):
        if self._access_token is None:
            raise InvalidAuth("Not authenticated")
        if self._token_expiry and asyncio.get_running_loop().time() > self._token_expiry - 60:
            await self.async_refresh_access_token()

class CannotConnect(Exception):
    """Connection error."""

class InvalidAuth(Exception):
    """Auth error."""

class APIError(Exception):
    """Generic API error."""
