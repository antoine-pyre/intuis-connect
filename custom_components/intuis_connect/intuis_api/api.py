"""Async API client for Intuis Connect cloud."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from ..entity.intuis_home import IntuisHome
from ..utils.const import (
    BASE_URLS,
    AUTH_PATH,
    HOMESDATA_PATH,
    HOMESTATUS_PATH,
    SETSTATE_PATH,
    HOMEMEASURE_PATH,
    ROOMMEASURE_PATH,
    ENERGY_MEASURE_TYPES,
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
    SYNCHOMESCHEDULE_PATH,
    CONFIG_PATH,
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
            self,
            session: aiohttp.ClientSession,
            home_id: str | None = None,
            debug: bool = False,
    ) -> None:
        """Initialize the API client."""
        self._session = session
        self._base_url: str = BASE_URLS[0]
        self.home_id: str | None = home_id
        self.home_timezone: str = "GMT"
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expiry: float | None = None
        self._debug: bool = debug
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
        if self._debug:
            _LOGGER.debug("Ensuring access token is valid")
        if self._access_token is None:
            _LOGGER.error("No access token available, authentication required")
            raise InvalidAuth("No access token – login first")
        if self._expiry and asyncio.get_running_loop().time() > self._expiry - 60:
            if self._debug:
                _LOGGER.debug("Access token expired or about to expire, refreshing token")
            await self.async_refresh_access_token()
        else:
            _LOGGER.debug("Access token is valid")

    def _save_tokens(self, data: dict[str, Any]) -> None:
        """Save the tokens and expiry time from an auth response."""
        if self._debug:
            _LOGGER.debug("Saving tokens, expires in %s seconds", data.get("expires_in"))
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        self._expiry = asyncio.get_running_loop().time() + data.get("expires_in", 10800)

    async def _async_request(
            self, method: str, path: str, retry: bool = True, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Make a request and handle token refresh with limited retries and timeouts.

        Retries:
        - Network-level errors (CannotConnect/TimeoutError): up to 3 attempts with backoff
        - HTTP 5xx and 429: up to 3 attempts with backoff
        - HTTP 401: single token refresh then one retry (existing behavior)
        """
        await self._ensure_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"

        url = f"{self._base_url}{path}"
        if self._debug:
            _LOGGER.debug("Making API request: %s %s", method, url)

        # Default timeout if not provided
        timeout = kwargs.pop("timeout", 20)

        attempts = 3
        delay = 1.5
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                resp = await self._session.request(
                    method, url, headers=headers, timeout=timeout, **kwargs
                )

                # Handle token refresh on 401 once (without counting towards attempts)
                if resp.status == 401 and retry:
                    _LOGGER.warning(
                        "Request unauthorized (401), refreshing token and retrying."
                    )
                    await self.async_refresh_access_token()
                    return await self._async_request(method, path, retry=False, **kwargs)

                # Retry on rate limiting and server errors
                if resp.status in (429,) or 500 <= resp.status < 600:
                    if attempt < attempts:
                        _LOGGER.warning(
                            "Server responded %s for %s %s (attempt %s/%s). Retrying in %.1fs",
                            resp.status,
                            method,
                            path,
                            attempt,
                            attempts,
                            delay,
                        )
                        try:
                            await resp.release()
                        finally:
                            await asyncio.sleep(delay)
                            delay *= 2
                        continue
                    # No more attempts
                    resp.raise_for_status()

                resp.raise_for_status()
                return resp

            except aiohttp.ClientResponseError as e:
                # Non-retriable client errors (4xx other than 429/401)
                _LOGGER.error("API request failed for %s: %s", path, e)
                raise APIError(f"Request failed for {path}: {e.status}") from e
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exc = e
                if attempt < attempts:
                    _LOGGER.warning(
                        "Network error on %s %s (attempt %s/%s): %s. Retrying in %.1fs",
                        method,
                        path,
                        attempt,
                        attempts,
                        repr(e),
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                _LOGGER.error("Cannot connect to API for %s after %s attempts: %s", path, attempts, e)
                raise CannotConnect(f"Cannot connect for {path}") from e

        # Should not reach here
        assert last_exc is not None
        raise CannotConnect(f"Cannot connect for {path}") from last_exc

    # ---------- auth ------------------------------------------------------------
    async def async_login(self, username: str, password: str) -> list[dict[str, Any]]:
        """Log in to the Intuis Connect service.

        Returns a list of available homes: [{"id": ..., "name": ..., "timezone": ...}, ...]
        """
        if self._debug:
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
                if self._debug:
                    _LOGGER.debug("Trying authentication endpoint %s", base + AUTH_PATH)
                async with self._session.post(
                        f"{base}{AUTH_PATH}", data=payload, timeout=20
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.warning(
                            "Login failed on %s status %s", base, resp.status
                        )
                        continue
                    data = await resp.json()
                    if "access_token" in data:
                        if self._debug:
                            _LOGGER.debug("Login successful on %s", base)
                        self._base_url = base
                        self._save_tokens(data)
                        break
                    else:
                        _LOGGER.warning(
                            "Login response on %s did not contain access_token", base
                        )
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                _LOGGER.warning("Client error during login on %s: %s", base, e)
                continue
        else:
            _LOGGER.error("Unable to log in on any cluster")
            raise CannotConnect("Unable to log in on any cluster")

        # Fetch all available homes
        if self._debug:
            _LOGGER.debug("Retrieving all homes post-login")
        homes = await self.async_get_all_homes()
        if not homes:
            _LOGGER.error("Login completed but no home associated with account")
            raise InvalidAuth("No home associated with account")
        if self._debug:
            _LOGGER.debug("Login completed, found %d homes", len(homes))
        return homes

    async def async_refresh_access_token(self) -> None:
        """Refresh the access token."""
        if self._debug:
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
    async def async_get_all_homes(self) -> list[dict[str, Any]]:
        """Fetch all homes from the API.

        Returns a list of dicts with home info:
        [{"id": "...", "name": "...", "timezone": "..."}, ...]
        """
        _LOGGER.debug("Fetching all homes from %s", self._base_url + HOMESDATA_PATH)
        async with await self._async_request("get", HOMESDATA_PATH) as resp:
            data = await resp.json()

        homes_raw = data.get("body", {}).get("homes", [])
        if not homes_raw:
            _LOGGER.error("No homes found in API response: %s", data)
            raise APIError("No homes found")

        homes = []
        for home in homes_raw:
            homes.append({
                "id": home["id"],
                "name": home.get("name", f"Home {home['id'][:8]}"),
                "timezone": home.get("timezone", "GMT"),
            })

        _LOGGER.debug("Found %d homes: %s", len(homes), [h["name"] for h in homes])
        return homes

    async def async_get_homes_data(self, target_home_id: str | None = None) -> IntuisHome:
        """Fetch homes data from the API.

        Args:
            target_home_id: If provided, fetch data for this specific home.
                           If None, use self.home_id or fall back to first home.
        """
        _LOGGER.debug("Fetching homes data from %s", self._base_url + HOMESDATA_PATH)
        async with await self._async_request("get", HOMESDATA_PATH) as resp:
            data = await resp.json()

        homes = data.get("body", {}).get("homes", [])
        if not homes:
            _LOGGER.error("Homes data response is empty or malformed: %s", data)
            raise APIError("Empty homesdata response")

        # Find the target home
        home = None
        search_id = target_home_id or self.home_id

        if search_id:
            for h in homes:
                if h["id"] == search_id:
                    home = h
                    break
            if not home:
                _LOGGER.error("Home %s not found in API response", search_id)
                raise APIError(f"Home {search_id} not found")
        else:
            # Fall back to first home (backward compatible)
            home = homes[0]

        self.home_id = home["id"]
        self.home_timezone = home.get("timezone", "GMT")
        _LOGGER.debug(
            "Home id set to %s with timezone %s", self.home_id, self.home_timezone
        )
        return IntuisHome.from_api(home)

    async def async_get_home_status(self) -> dict[str, Any]:
        """Fetch the status of the home."""
        if self._debug:
            _LOGGER.debug("Fetching home status for home_id=%s", self.home_id)
        payload = {"home_id": self.home_id}
        async with await self._async_request(
                "post", HOMESTATUS_PATH, data=payload
        ) as resp:
            result = await resp.json()
        if self._debug:
            _LOGGER.debug("Home status response: %s", result)
        home = result.get("body", {}).get("home", {})
        if not home:
            _LOGGER.error("Home status response is empty or malformed: %s", result)
            raise APIError("Empty home status response")
        return home


    async def async_get_config(self) -> dict[str, Any]:
        """Fetch the configuration of the home."""
        _LOGGER.debug("Fetching home configurations for home_id=%s", self.home_id)
        payload = {"home_id": self.home_id}
        async with await self._async_request(
            "post", CONFIG_PATH, data=payload
        ) as resp:
            result = await resp.json()
        _LOGGER.debug("Home configurations response: %s", result)
        home = result.get("body", {}).get("home", {})
        if not home:
            _LOGGER.error("Home configurations response is empty or malformed: %s", result)
            raise APIError("Empty home configurations response")
        return home

    async def async_set_room_state(
            self,
            room_id: str,
            mode: str,
            temp: float | None = None,
            duration: int | None = None,
    ) -> None:
        """Send setstate command for one room."""
        if self._debug:
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
        if self._debug:
            _LOGGER.debug("Room %s state set to mode=%s, temp=%s", room_id, mode, temp)

    async def async_get_energy_measures(
        self, rooms: list[dict[str, str]], date_begin: int, date_end: int,
        scale: str = "1day"
    ) -> dict[str, float]:
        """Return energy in Wh for multiple rooms.

        Uses /api/getroommeasure endpoint with form-encoded data.
        Requests all tariff types and sums non-null values.

        Args:
            rooms: List of dicts with keys 'id' and 'bridge' for each room.
            date_begin: Unix epoch timestamp for start of period.
            date_end: Unix epoch timestamp for end of period.
            scale: Time scale for measures (5min, 30min, 1hour, 1day, etc.)

        Returns:
            Dict mapping room_id to energy in Wh.
        """
        if not rooms:
            return {}

        if self._debug:
            _LOGGER.debug(
                "Fetching energy measures for %d rooms from %s to %s",
                len(rooms),
                date_begin,
                date_end,
            )

        result: dict[str, float] = {}

        for room in rooms:
            room_id = room["id"]
            try:
                energy = await self._async_get_room_energy(
                    room_id, date_begin, date_end, scale
                )
                result[room_id] = energy
            except Exception as e:
                _LOGGER.warning(
                    "Failed to get energy for room %s: %s", room_id, e
                )
                result[room_id] = 0.0

        return result

    async def _async_get_room_energy(
        self, room_id: str, date_begin: int, date_end: int, scale: str = "1day"
    ) -> float:
        """Get energy consumption for a single room.

        Args:
            room_id: The room ID.
            date_begin: Unix epoch timestamp for start of period.
            date_end: Unix epoch timestamp for end of period.
            scale: Time scale for measures.

        Returns:
            Energy in Wh.
        """
        # Use form-encoded data (not JSON) - required by this endpoint
        form_data = {
            "home_id": self.home_id,
            "room_id": room_id,
            "scale": scale,
            "type": ENERGY_MEASURE_TYPES,
            "date_begin": str(date_begin),
            "date_end": str(date_end),
        }

        try:
            async with await self._async_request(
                "post",
                ROOMMEASURE_PATH,
                data=form_data,  # Form-encoded, not JSON
            ) as resp:
                data = await resp.json()

            if self._debug:
                _LOGGER.debug("Room %s energy response: %s", room_id, data)

            # Sum all non-null values from all measure entries
            # Response format: {"body": [{"beg_time": ..., "value": [[v1, v2, v3, v4], ...]}, ...]}
            total_energy = 0.0
            body = data.get("body", [])

            for measure in body:
                values = measure.get("value", [])
                for val_set in values:
                    # val_set contains [sum_energy_elec, $0, $1, $2]
                    # Sum all non-null values
                    for val in val_set:
                        if val is not None:
                            total_energy += float(val)

            return total_energy

        except (APIError, KeyError, ValueError, TypeError) as e:
            _LOGGER.warning(
                "Energy measure request failed for room %s: %s",
                room_id,
                e,
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

    async def async_sync_schedule(
        self,
        schedule_id: str,
        schedule_name: str,
        schedule_type: str,
        timetable: list[dict[str, int]],
        zones: list[dict[str, Any]],
        away_temp: int | None = None,
        hg_temp: int | None = None,
    ) -> None:
        """Sync a schedule to the API (create/update).

        This uses the synchomeschedule endpoint which requires a specific format:
        - home_id at root level
        - schedule fields (id, name, type) at root level
        - timetable: list of {zone_id, m_offset} entries
        - zones: list with only rooms_temp (not rooms) to avoid API error

        Args:
            schedule_id: The schedule ID.
            schedule_name: The schedule name.
            schedule_type: The schedule type ('therm' or 'electricity').
            timetable: List of timetable entries [{zone_id: int, m_offset: int}, ...].
            zones: List of zone dicts with only rooms_temp field.
            away_temp: Away temperature (for therm schedules).
            hg_temp: Frost protection temperature (for therm schedules).
        """
        if self._debug:
            _LOGGER.debug(
                "Syncing schedule %s (%s) with %d timetable entries and %d zones",
                schedule_name,
                schedule_id,
                len(timetable),
                len(zones),
            )

        # Build payload in the required format
        payload: dict[str, Any] = {
            "home_id": self.home_id,
            "id": schedule_id,
            "name": schedule_name,
            "type": schedule_type,
            "timetable": timetable,
            "zones": zones,
        }

        # Add therm-specific fields
        if schedule_type == "therm":
            if away_temp is not None:
                payload["away_temp"] = away_temp
            if hg_temp is not None:
                payload["hg_temp"] = hg_temp

        # Make direct request to handle error responses properly
        await self._ensure_token()
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}{SYNCHOMESCHEDULE_PATH}"

        _LOGGER.debug("Sync schedule payload: %s", payload)

        async with self._session.post(url, json=payload, headers=headers, timeout=20) as resp:
            result = await resp.json()
            _LOGGER.debug("Sync schedule response (status=%s): %s", resp.status, result)

            # Check for API error in response body
            if "error" in result:
                error = result["error"]
                raise APIError(
                    f"sync_schedule failed: {error.get('message', 'Unknown error')} "
                    f"(code: {error.get('code')})"
                )

            if resp.status not in (200, 204):
                raise APIError(f"sync_schedule failed with status {resp.status}: {result}")

        _LOGGER.info("Schedule %s synced successfully", schedule_name)
