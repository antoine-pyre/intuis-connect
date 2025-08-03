"""API client for Intuis Connect (Muller Intuitiv + Netatmo)."""
from __future__ import annotations
import asyncio, logging, time
from typing import Any, Dict, Optional

import aiohttp

from .const import (
    BASE_URLS, AUTH_PATH, HOMESDATA_PATH, HOMESTATUS_PATH, SETSTATE_PATH,
    CLIENT_ID, CLIENT_SECRET, AUTH_SCOPE, USER_PREFIX, APP_TYPE, APP_VERSION
)

_LOGGER = logging.getLogger(__name__)

class CannotConnect(Exception):
    """Error connecting to Intuis API."""

class InvalidAuth(Exception):
    """Invalid credentials or token."""

class APIError(Exception):
    """Generic API error."""

class IntuisAPI:
    """Thin async client for Intuis/Netatmo endpoints."""

    def __init__(self, session: aiohttp.ClientSession, home_id: str | None = None):
        self._session = session
        self.home_id: str | None = home_id
        self.home_timezone: str | None = None
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: float | None = None
        self._base_url: str = BASE_URLS[0]

    # ------------------------------------------------------------------ auth
    async def async_login(self, username: str, password: str) -> str:
        """Owner-login: get access & refresh token and remember home id."""
        for base in BASE_URLS:
            try:
                await self._async_do_login(base, username, password)
                self._base_url = base
                break
            except CannotConnect:
                continue
        else:
            raise CannotConnect("All clusters unreachable")

        await self.async_get_homes_data()
        if not self.home_id:
            raise InvalidAuth("No home associated with account")
        return self.home_id

    async def _async_do_login(self, base: str, username: str, password: str):
        payload = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": AUTH_SCOPE,
            "user_prefix": USER_PREFIX,
            "app_version": APP_VERSION,
        }
        url = f"{base}{AUTH_PATH}"
        async with self._session.post(url, data=payload, timeout=15) as resp:
            if resp.status != 200:
                _LOGGER.debug("Login failed on %s status %s", base, resp.status)
                raise CannotConnect()
            data = await resp.json()
        if "access_token" not in data:
            raise InvalidAuth(data.get("error_description") or "Invalid credentials")
        self._store_tokens(data)

    def _store_tokens(self, data: Dict[str, Any]):
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        expires = data.get("expires_in", 10800)
        self._token_expiry = asyncio.get_running_loop().time() + expires

    async def async_refresh_access_token(self):
        if not self._refresh_token:
            raise InvalidAuth("No refresh token")
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "user_prefix": USER_PREFIX,
        }
        async with self._session.post(f"{self._base_url}{AUTH_PATH}", data=payload, timeout=10) as resp:
            if resp.status != 200:
                raise InvalidAuth("Refresh failed")
            data = await resp.json()
        self._store_tokens(data)

    async def _ensure_token(self):
        if self._access_token is None:
            raise InvalidAuth("Not authenticated")
        if self._token_expiry and asyncio.get_running_loop().time() > self._token_expiry - 60:
            await self.async_refresh_access_token()

    # ------------------------------------------------------------- data calls
    async def async_get_homes_data(self) -> Dict[str, Any]:
        await self._ensure_token()
        headers = {"Authorization": f"Bearer {self._access_token}"}
        async with self._session.get(f"{self._base_url}{HOMESDATA_PATH}", headers=headers, timeout=10) as resp:
            if resp.status == 401:
                await self.async_refresh_access_token()
                headers["Authorization"] = f"Bearer {self._access_token}"
                resp = await self._session.get(f"{self._base_url}{HOMESDATA_PATH}", headers=headers, timeout=10)
            if resp.status != 200:
                raise APIError("homesdata failed")
            data = await resp.json()
        homes = data.get("body", {}).get("homes", [])
        if not homes:
            raise APIError("No homes in response")
        if not self.home_id:
            self.home_id = homes[0]["id"]
        self.home_timezone = homes[0].get("timezone", "GMT")
        return homes[0]

    async def async_get_home_status(self) -> Dict[str, Any]:
        await self._ensure_token()
        headers = {"Authorization": f"Bearer {self._access_token}"}
        payload = {"home_id": self.home_id}
        async with self._session.post(f"{self._base_url}{HOMESTATUS_PATH}", headers=headers, data=payload, timeout=10) as resp:
            if resp.status == 401:
                await self.async_refresh_access_token()
                headers["Authorization"] = f"Bearer {self._access_token}"
                resp = await self._session.post(f"{self._base_url}{HOMESTATUS_PATH}", headers=headers, data=payload, timeout=10)
            if resp.status != 200:
                raise APIError("homestatus failed")
            return await resp.json()

    async def async_set_room_state(self, room_id: str, mode: str, temp: float | None = None, duration: int | None = None):
        await self._ensure_token()
        room_payload: Dict[str, Any] = {"id": room_id, "therm_setpoint_mode": mode}
        if mode == "manual":
            if temp is None:
                raise APIError("Manual mode requires temperature")
            end_time = int(time.time()) + (duration or 120) * 60
            room_payload.update({
                "therm_setpoint_temperature": float(temp),
                "therm_setpoint_end_time": end_time,
            })
        payload = {
            "app_type": APP_TYPE,
            "app_version": APP_VERSION,
            "home": {
                "id": self.home_id,
                "rooms": [room_payload],
                "timezone": self.home_timezone or "GMT",
            },
        }
        headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}
        async with self._session.post(f"{self._base_url}{SETSTATE_PATH}", headers=headers, json=payload, timeout=10) as resp:
            if resp.status == 401:
                await self.async_refresh_access_token()
                headers["Authorization"] = f"Bearer {self._access_token}"
                resp = await self._session.post(f"{self._base_url}{SETSTATE_PATH}", headers=headers, json=payload, timeout=10)
            if resp.status != 200:
                raise APIError("setstate failed")
            return await resp.json()
