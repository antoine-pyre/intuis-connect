"""Async API client for Intuis Connect cloud."""
from __future__ import annotations

import asyncio
import logging
import time
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
        _LOGGER.debug("IntuisAPI initialized with home_id=%s", home_id)

    # ---------- internal helpers ------------------------------------------------
    async def _ensure_token(self):
        _LOGGER.debug("Ensuring access token is valid")
        if self._access_token is None:
            _LOGGER.error("No access token available, authentication required")
            raise InvalidAuth("No access token – login first")
        if self._expiry and asyncio.get_running_loop().time() > self._expiry - 60:
            _LOGGER.debug("Access token expired or about to expire, refreshing token")
            await self.async_refresh_access_token()
        else:
            _LOGGER.debug("Access token is valid")

    def _save_tokens(self, data: Dict[str, Any]):
        _LOGGER.debug("Saving tokens, expires in %s seconds", data.get("expires_in"))
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        self._expiry = asyncio.get_running_loop().time() + data.get("expires_in", 10800)

    # ---------- auth ------------------------------------------------------------
    async def async_login(self, username: str, password: str) -> str:
        _LOGGER.debug("Attempting login for user %s", username)
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
                _LOGGER.debug("Trying authentication endpoint %s", base + AUTH_PATH)
                async with self._session.post(f"{base}{AUTH_PATH}", data=payload, timeout=15) as resp:
                    if resp.status != 200:
                        _LOGGER.warning("Login failed on %s status %s", base, resp.status)
                        continue
                    data = await resp.json()
                    if "access_token" in data:
                        _LOGGER.debug("Login successful on %s", base)
                        self._base_url = base
                        self._save_tokens(data)
                        break
                    else:
                        _LOGGER.warning("Login response on %s did not contain access_token", base)
            except aiohttp.ClientError as e:
                _LOGGER.warning("Client error during login on %s: %s", base, e)
                continue
        else:
            _LOGGER.error("Unable to log in on any cluster")
            raise CannotConnect("Unable to log in on any cluster")

        _LOGGER.debug("Retrieving homes data post-login for token validation")
        await self.async_get_homes_data()
        if not self.home_id:
            _LOGGER.error("Login completed but no home associated with account")
            raise InvalidAuth("No home associated with account")
        _LOGGER.debug("Login completed, home_id=%s", self.home_id)
        return self.home_id

    async def async_refresh_access_token(self):
        _LOGGER.debug("Refreshing access token using refresh_token=%s", self._refresh_token)
        if not self._refresh_token:
            _LOGGER.error("No refresh token saved, cannot refresh access token")
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
                _LOGGER.error("Token refresh failed with status %s", resp.status)
                raise InvalidAuth("Token refresh failed")
            data = await resp.json()
            _LOGGER.debug("Token refresh successful, new expiry in %s seconds", data.get("expires_in"))
            self._save_tokens(data)

    # ---------- data endpoints ---------------------------------------------------
    async def async_get_homes_data(self) -> Dict[str, Any]:
        _LOGGER.debug("Fetching homes data from %s", self._base_url + HOMESDATA_PATH)
        await self._ensure_token()
        headers = {"Authorization": f"Bearer {self._access_token}"}
        async with self._session.get(f"{self._base_url}{HOMESDATA_PATH}", headers=headers, timeout=10) as resp:
            if resp.status == 401:
                _LOGGER.warning("Homes data request unauthorized, refreshing token and retrying")
                await self.async_refresh_access_token()
                headers["Authorization"] = f"Bearer {self._access_token}"
                resp = await self._session.get(f"{self._base_url}{HOMESDATA_PATH}", headers=headers, timeout=10)
            if resp.status != 200:
                _LOGGER.error("Homes data request failed with status %s", resp.status)
                raise APIError("homesdata failed")
            data = await resp.json()
        if not data.get("body", {}).get("homes"):
            _LOGGER.error("Homes data response is empty or malformed: %s", data)
            raise APIError("Empty homesdata response")
        _LOGGER.debug("Homes data received: %s", data)
        home = data.get("body", {}).get("homes", [])[0]
        self.home_id = home["id"]
        self.home_timezone = home.get("timezone", "GMT")
        _LOGGER.debug("Home id set to %s with timezone %s", self.home_id, self.home_timezone)
        return home

    async def async_get_home_status(self) -> Dict[str, Any]:
        _LOGGER.debug("Fetching home status for home_id=%s", self.home_id)
        await self._ensure_token()
        headers = {"Authorization": f"Bearer {self._access_token}"}
        payload = {"home_id": self.home_id}
        async with self._session.post(f"{self._base_url}{HOMESTATUS_PATH}", headers=headers, data=payload,
                                      timeout=10) as resp:
            if resp.status == 401:
                await self.async_refresh_access_token()
                headers["Authorization"] = f"Bearer {self._access_token}"
                resp = await self._session.post(f"{self._base_url}{HOMESTATUS_PATH}", headers=headers, data=payload,
                                                timeout=10)
            if resp.status != 200:
                _LOGGER.error("Home status request failed with status %s", resp.status)
                raise APIError("homestatus failed")
            result = await resp.json()
        _LOGGER.debug("Home status response: %s", result)
        return result

    async def async_set_child_lock(self, module_id: str, locked: bool):
        _LOGGER.debug("Setting child lock for module %s to %s", module_id, locked)
        await self._ensure_token()
        payload = {
            "app_type": APP_TYPE,
            "app_version": APP_VERSION,
            "home": {
                "id": self.home_id,
                "modules": [{"id": module_id, "keypad_locked": 1 if locked else 0}],
            },
        }
        headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}
        async with self._session.post(
                f"{self._base_url}{SETSTATE_PATH}", json=payload, headers=headers, timeout=10
        ) as resp:
            if resp.status not in (200, 204):
                _LOGGER.error("Child-lock setstate failed with status %s", resp.status)
                raise APIError(f"Child-lock failed ({resp.status})")
            _LOGGER.info("Child lock for module %s set to %s", module_id, locked)

    async def async_set_room_state(self, room_id: str, mode: str, temp: float | None = None,
                                   duration: int | None = None):
        _LOGGER.debug("Setting room state for room %s: mode=%s, temp=%s, duration=%s", room_id, mode, temp, duration)
        """Send setstate command for one room."""
        await self._ensure_token()
        room_payload: Dict[str, Any] = {"id": room_id, "therm_setpoint_mode": mode}
        if mode == "manual":
            if temp is None:
                raise APIError("Manual mode requires temperature")
            end = int(time.time()) + (duration or 120) * 60
            room_payload.update({"therm_setpoint_temperature": float(temp), "therm_setpoint_end_time": end})
        payload = {
            "app_type": APP_TYPE,
            "app_version": APP_VERSION,
            "home": {"id": self.home_id, "rooms": [room_payload], "timezone": self.home_timezone},
        }
        headers = {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}
        async with self._session.post(f"{self._base_url}{SETSTATE_PATH}", headers=headers, json=payload,
                                      timeout=10) as resp:
            if resp.status not in (200, 204):
                _LOGGER.error("Set room state failed with status %s", resp.status)
                raise APIError("setstate failed")
            _LOGGER.info("Room %s state set to mode=%s, temp=%s", room_id, mode, temp)

    async def async_get_home_measure(self, room_id: str, date_iso: str) -> float:
        _LOGGER.debug("Fetching home measure for room %s on date %s", room_id, date_iso)
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
        async with self._session.post(f"{self._base_url}{HOMEMEASURE_PATH}", headers=headers, data=payload,
                                      timeout=10) as resp:
            if resp.status != 200:
                _LOGGER.warning("Home measure request failed with status %s, returning 0.0", resp.status)
                return 0.0
            data = await resp.json()
        _LOGGER.debug("Home measure data received: %s", data)
        measures = data.get("body", {}).get("measure", [])
        if not measures:
            _LOGGER.debug("No measure data in response for room %s on date %s", room_id, date_iso)
            return 0.0
        return float(measures[0][1])
