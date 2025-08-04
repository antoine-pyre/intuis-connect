
"""Async API client for Intuis Connect cloud."""
from __future__ import annotations

import asyncio, logging, time
from datetime import datetime
from typing import Any, Dict

import aiohttp

from .const import (
    BASE_URLS, AUTH_PATH, HOMESDATA_PATH, HOMESTATUS_PATH, SETSTATE_PATH, HOMEMEASURE_PATH,
    CLIENT_ID, CLIENT_SECRET, AUTH_SCOPE, USER_PREFIX, APP_TYPE, APP_VERSION
)

_LOGGER = logging.getLogger(__name__)

class CannotConnect(Exception):
    """Errors related to connectivity."""

class InvalidAuth(Exception):
    """Authentication/Token errors."""

class APIError(Exception):
    """Generic API errors."""

class IntuisAPI:
    """Minimal client wrapping the Intuis Netatmo endpoints."""
    def __init__(self, session: aiohttp.ClientSession, home_id: str | None = None):
        self._session = session
        self._base_url: str = BASE_URLS[0]
        self.home_id: str | None = home_id
        self.home_timezone = "GMT"
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expiry: float | None = None

    # ---------- internal helpers ------------------------------------------------
    async def _ensure_token(self):
        if self._access_token is None:
            raise InvalidAuth("No access token – login first")
        if self._expiry and asyncio.get_running_loop().time() > self._expiry - 60:
            await self.async_refresh_access_token()

    def _save_tokens(self, data: Dict[str, Any]):
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        self._expiry = asyncio.get_running_loop().time() + data.get("expires_in", 10800)

    # ---------- auth ------------------------------------------------------------
    async def async_login(self, username: str, password: str) -> str:
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
        for base in BASE_URLS:
            try:
                async with self._session.post(f"{base}{AUTH_PATH}", data=payload, timeout=15) as resp:
                    if resp.status != 200:
                        _LOGGER.debug("Login failed on %s status %s", base, resp.status)
                        continue
                    data = await resp.json()
            except aiohttp.ClientError:
                continue
            if "access_token" in data:
                self._base_url = base
                self._save_tokens(data)
                break
        else:
            raise CannotConnect("Unable to log in on any cluster")

        await self.async_get_homes_data()
        if not self.home_id:
            raise InvalidAuth("No home associated with account")
        return self.home_id

    async def async_refresh_access_token(self):
        if not self._refresh_token:
            raise InvalidAuth("No refresh token saved")
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "user_prefix": USER_PREFIX,
        }
        async with self._session.post(f"{self._base_url}{AUTH_PATH}", data=payload, timeout=10) as resp:
            if resp.status != 200:
                raise InvalidAuth("Token refresh failed")
            data = await resp.json()
        self._save_tokens(data)

    # ---------- data endpoints ---------------------------------------------------
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
        home = data.get("body", {}).get("homes", [])[0]
        self.home_id = home["id"]
        self.home_timezone = home.get("timezone", "GMT")
        return home

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

    async def async_set_child_lock(self, module_id: str, locked: bool):
        await self._ensure_token()
        payload = {
            "app_type": APP_TYPE,
            "home": {
                "id": self.home_id,
                "modules": [
                    {"id": module_id, "keypad_locked": 1 if locked else 0}
                ],
            },
        }
        headers = {"Authorization": f"Bearer {self._access_token}"}
        async with self._session.post(
                f"{self._base_url}{SETSTATE_PATH}", json=payload, headers=headers, timeout=10
        ) as resp:
            if resp.status not in (200, 204):
                raise APIError(f"Child-lock failed ({resp.status})")


    async def async_set_child_lock(self, room_id: str, locked: bool):
        await self._ensure_token()
        payload = {
            "app_type": APP_TYPE,
            "app_version": APP_VERSION,
            "home": {"id": self.home_id, "modules": [{"id": room_id, "keypad_lock": 1 if locked else 0}]},
        }
        headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}
        async with self._session.post(f"{self._base_url}{SETSTATE_PATH}", headers=headers, json=payload, timeout=10) as resp:
            if resp.status not in (200, 204):
                raise APIError("child-lock setstate failed")

    async def async_get_home_measure(self, room_id: str, date_iso: str) -> float:
        """Return kWh for given room and date (YYYY-MM-DD) or 0.0 on failure."""
        await self._ensure_token()
        payload = {
            "home_id": self.home_id,
            "room_id": room_id,
            "scale": "1day",
            "type": "sum_energy",
            "date_begin": date_iso,
            "date_end": date_iso,
        }
        headers = {"Authorization": f"Bearer {self._access_token}"}
        async with self._session.post(f"{self._base_url}{HOMEMEASURE_PATH}", headers=headers, data=payload, timeout=10) as resp:
            if resp.status != 200:
                return 0.0
            data = await resp.json()
        measures = data.get("body", {}).get("measure", [])
        return float(measures[0][1]) if measures else 0.0
