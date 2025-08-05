"""Async API client for Intuis Connect cloud."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .const import (
    BASE_URLS,
    AUTH_PATH,
    HOMESDATA_PATH,
    HOMESTATUS_PATH,
    SETSTATE_PATH,
    HOMEMEASURE_PATH,
    CLIENT_ID,
    CLIENT_SECRET,
    AUTH_SCOPE,
    USER_PREFIX,
    APP_TYPE,
    APP_VERSION,
    DEFAULT_MANUAL_DURATION,
    ENERGY_BASE,
    GET_SCHEDULE_PATH,
    SET_SCHEDULE_PATH,
    DELETE_SCHEDULE_PATH,
    SWITCH_SCHEDULE_PATH,
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

    def __init__(
            self, session: aiohttp.ClientSession, home_id: str | None = None
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._base_url: str = BASE_URLS[0]
        self.home_id: str | None = home_id
        self.home_timezone: str = "GMT"
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expiry: float | None = None
        _LOGGER.debug("IntuisAPI initialized with home_id=%s", home_id)

    @property
    def refresh_token(self) -> str | None:
        """Return the current refresh token."""
        return self._refresh_token

    @refresh_token.setter
    def refresh_token(self, value: str) -> None:
        """Set the refresh token."""
        self._refresh_token = value

    # ---------- internal helpers ------------------------------------------------
    async def _ensure_token(self) -> None:
        """Ensure the access token is valid, refreshing it if necessary."""
        _LOGGER.debug("Ensuring access token is valid")
        if self._access_token is None:
            _LOGGER.error("No access token available, authentication required")
            raise InvalidAuth("No access token – login first")
        if self._expiry and asyncio.get_running_loop().time() > self._expiry - 60:
            _LOGGER.debug("Access token expired or about to expire, refreshing token")
            await self.async_refresh_access_token()
        else:
            _LOGGER.debug("Access token is valid")

    def _save_tokens(self, data: dict[str, Any]) -> None:
        """Save the tokens and expiry time from an auth response."""
        _LOGGER.debug("Saving tokens, expires in %s seconds", data.get("expires_in"))
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        self._expiry = asyncio.get_running_loop().time() + data.get("expires_in", 10800)

    async def _async_request(
            self, method: str, path: str, retry: bool = True, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Make a request and handle token refresh."""
        await self._ensure_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"

        url = f"{self._base_url}{path}"
        _LOGGER.debug("Making API request: %s %s", method, url)

        try:
            resp = await self._session.request(
                method, url, headers=headers, timeout=10, **kwargs
            )

            if resp.status == 401 and retry:
                _LOGGER.warning(
                    "Request unauthorized (401), refreshing token and retrying."
                )
                await self.async_refresh_access_token()
                # Call self again, but without retry to avoid infinite loop
                return await self._async_request(method, path, retry=False, **kwargs)

            resp.raise_for_status()
            return resp

        except aiohttp.ClientResponseError as e:
            _LOGGER.error("API request failed for %s: %s", path, e)
            raise APIError(f"Request failed for {path}: {e.status}") from e
        except aiohttp.ClientError as e:
            _LOGGER.error("Cannot connect to API for %s: %s", path, e)
            raise CannotConnect(f"Cannot connect for {path}") from e

    # ---------- auth ------------------------------------------------------------
    async def async_login(self, username: str, password: str) -> str:
        """Log in to the Intuis Connect service."""
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
                async with self._session.post(
                        f"{base}{AUTH_PATH}", data=payload, timeout=15
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.warning(
                            "Login failed on %s status %s", base, resp.status
                        )
                        continue
                    data = await resp.json()
                    if "access_token" in data:
                        _LOGGER.debug("Login successful on %s", base)
                        self._base_url = base
                        self._save_tokens(data)
                        break
                    else:
                        _LOGGER.warning(
                            "Login response on %s did not contain access_token", base
                        )
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

    async def async_refresh_access_token(self) -> None:
        """Refresh the access token."""
        _LOGGER.debug(
            "Refreshing access token using refresh_token=%s", self._refresh_token
        )
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
        async with self._session.post(
                f"{self._base_url}{AUTH_PATH}", data=payload, timeout=10
        ) as resp:
            if resp.status != 200:
                _LOGGER.error("Token refresh failed with status %s", resp.status)
                raise InvalidAuth("Token refresh failed")
            data = await resp.json()
            _LOGGER.debug(
                "Token refresh successful, new expiry in %s seconds",
                data.get("expires_in"),
            )
            self._save_tokens(data)

    # ---------- data endpoints ---------------------------------------------------
    async def async_get_homes_data(self) -> dict[str, Any]:
        """Fetch homes data from the API."""
        _LOGGER.debug("Fetching homes data from %s", self._base_url + HOMESDATA_PATH)
        async with await self._async_request("get", HOMESDATA_PATH) as resp:
            data = await resp.json()

        if not data.get("body", {}).get("homes"):
            _LOGGER.error("Homes data response is empty or malformed: %s", data)
            raise APIError("Empty homesdata response")
        _LOGGER.debug("Homes data received: %s", data)
        home = data.get("body", {}).get("homes", [])[0]
        self.home_id = home["id"]
        self.home_timezone = home.get("timezone", "GMT")
        _LOGGER.debug(
            "Home id set to %s with timezone %s", self.home_id, self.home_timezone
        )
        return home

    async def async_get_home_status(self) -> dict[str, Any]:
        """Fetch the status of the home."""
        _LOGGER.debug("Fetching home status for home_id=%s", self.home_id)
        payload = {"home_id": self.home_id}
        async with await self._async_request(
                "post", HOMESTATUS_PATH, data=payload
        ) as resp:
            result = await resp.json()
        _LOGGER.debug("Home status response: %s", result)
        home = result.get("body", {}).get("home", {})
        if not home:
            _LOGGER.error("Home status response is empty or malformed: %s", result)
            raise APIError("Empty home status response")
        return home

    async def async_set_room_state(
            self,
            room_id: str,
            mode: str,
            temp: float | None = None,
            duration: int | None = None,
    ) -> None:
        """Send setstate command for one room."""
        _LOGGER.debug(
            "Setting room state for room %s: mode=%s, temp=%s, duration=%s",
            room_id,
            mode,
            temp,
            duration,
        )
        room_payload: dict[str, Any] = {"id": room_id, "therm_setpoint_mode": mode}
        if mode == "manual":
            if temp is None:
                raise APIError("Manual mode requires temperature")
            end = int(time.time()) + (duration or DEFAULT_MANUAL_DURATION) * 60
            room_payload.update(
                {"therm_setpoint_temperature": float(temp), "therm_setpoint_end_time": end}
            )
        payload = {
            "app_type": APP_TYPE,
            "app_version": APP_VERSION,
            "home": {
                "id": self.home_id,
                "rooms": [room_payload],
                "timezone": self.home_timezone,
            },
        }
        await self._async_request(
            "post",
            SETSTATE_PATH,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        _LOGGER.info("Room %s state set to mode=%s, temp=%s", room_id, mode, temp)

    async def async_get_home_measure(self, room_id: str, date_iso: str) -> float:
        """Return kWh for given room and date (YYYY-MM-DD) or 0.0 on failure."""
        _LOGGER.debug(
            "Fetching home measure for room %s on date %s", room_id, date_iso
        )
        payload = {
            "home_id": self.home_id,
            "room_id": room_id,
            "scale": "1day",
            "type": "sum_energy",
            "date_begin": date_iso,
            "date_end": date_iso,
        }
        try:
            async with await self._async_request(
                    "post", HOMEMEASURE_PATH, data=payload
            ) as resp:
                data = await resp.json()
            _LOGGER.debug("Home measure data received: %s", data)
            measures = data.get("body", {}).get("measure", [])
            if not measures:
                _LOGGER.debug(
                    "No measure data in response for room %s on date %s",
                    room_id,
                    date_iso,
                )
                return 0.0
            return float(measures[0][1])
        except APIError:
            _LOGGER.warning(
                "Home measure request failed for room %s on date %s, returning 0.0",
                room_id,
                date_iso,
                exc_info=True,
            )
            return 0.0

    async def async_get_schedule(
            self, home_id: str, schedule_id: int
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Fetch the full timetable for a given schedule.

        Returns a dict { room_id: [ { id, start, end, temp }, … ], … }.
        """
        await self._ensure_token()
        params = {"home_id": home_id, "schedule_id": schedule_id}
        url = f"{ENERGY_BASE}{GET_SCHEDULE_PATH}"
        async with self._session.get(url, params=params, timeout=10) as resp:
            if resp.status != 200:
                raise APIError(f"get_schedule failed (HTTP {resp.status})")
            body = await resp.json()
        rooms: dict[str, list[dict[str, Any]]] = {}
        for room in body.get("rooms", []):
            rid = room["room_id"]
            rooms[rid] = room.get("slots", [])
        return rooms

    async def async_set_schedule_slot(
            self,
            home_id: str,
            schedule_id: int,
            room_id: str,
            start: str,
            end: str,
            temperature: float,
    ) -> None:
        """Create or update a single timeslot in the given schedule."""
        await self._ensure_token()
        payload = {
            "home_id": home_id,
            "schedule_id": schedule_id,
            "zones": [
                {
                    "room_id": room_id,
                    "timetable": [{"start": start, "end": end, "temp": temperature}],
                }
            ],
        }
        url = f"{ENERGY_BASE}{SET_SCHEDULE_PATH}"
        async with self._session.post(url, json=payload, timeout=10) as resp:
            if resp.status not in (200, 204):
                raise APIError(f"set_schedule_slot failed (HTTP {resp.status})")

    async def async_delete_schedule_slot(self, home_id: str, slot_id: str) -> None:
        """Delete a specific schedule slot by its ID."""
        await self._ensure_token()
        params = {"home_id": home_id, "slot_id": slot_id}
        url = f"{ENERGY_BASE}{DELETE_SCHEDULE_PATH}"
        async with self._session.delete(url, params=params, timeout=10) as resp:
            if resp.status not in (200, 204):
                raise APIError(f"delete_schedule_slot failed (HTTP {resp.status})")

    async def async_switch_schedule(self, home_id: str, schedule_id: int) -> None:
        """Switch the active weekly schedule."""
        await self._ensure_token()
        payload = {"home_id": home_id, "schedule_id": schedule_id}
        url = f"{ENERGY_BASE}{SWITCH_SCHEDULE_PATH}"
        async with self._session.post(url, json=payload, timeout=10) as resp:
            if resp.status not in (200, 204):
                raise APIError(f"switch_schedule failed (HTTP {resp.status})")
