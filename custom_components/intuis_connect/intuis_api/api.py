"""Async API client for Intuis Connect cloud."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable

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
    DEFAULT_RATE_LIMIT_DELAY,
    DEFAULT_CIRCUIT_THRESHOLD,
    DEFAULT_MIN_REQUEST_DELAY,
    DEFAULT_RATE_LIMIT_MAX_DELAY,
    DEFAULT_RATE_LIMIT_ATTEMPTS,
)

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Errors related to connectivity."""


class InvalidAuth(Exception):
    """Authentication/Token errors."""


class APIError(Exception):
    """Generic API errors."""


class RateLimitError(Exception):
    """Rate limit (429) error with circuit breaker open."""


class RateLimitCircuitBreaker:
    """Prevents request storms when rate limited.

    After a threshold of consecutive 429 errors, opens the circuit
    to prevent further requests for an exponentially increasing cooldown period.
    """

    def __init__(
        self,
        threshold: int = DEFAULT_CIRCUIT_THRESHOLD,
        base_cooldown: float = 30.0,
        max_cooldown: float = 120.0,
    ) -> None:
        """Initialize the circuit breaker.

        Args:
            threshold: Number of consecutive 429s before circuit opens.
            base_cooldown: Initial cooldown duration in seconds.
            max_cooldown: Maximum cooldown duration in seconds.
        """
        self._threshold = threshold
        self._base_cooldown = base_cooldown
        self._max_cooldown = max_cooldown
        self._consecutive_429s = 0
        self._circuit_open_until: datetime | None = None
        self._on_rate_limit_callback: Callable[[], None] | None = None

    def set_rate_limit_callback(self, callback: Callable[[], None]) -> None:
        """Set callback to invoke when rate limited."""
        self._on_rate_limit_callback = callback

    def record_429(self) -> float:
        """Record a 429 error and return cooldown time if circuit opens.

        Returns:
            Cooldown time in seconds if circuit opened, 0 otherwise.
        """
        self._consecutive_429s += 1
        _LOGGER.debug(
            "Rate limit recorded. Consecutive 429s: %d/%d",
            self._consecutive_429s, self._threshold
        )

        if self._consecutive_429s >= self._threshold:
            # Calculate exponential cooldown
            multiplier = 2 ** (self._consecutive_429s - self._threshold)
            cooldown = min(self._base_cooldown * multiplier, self._max_cooldown)
            self._circuit_open_until = datetime.now() + timedelta(seconds=cooldown)
            _LOGGER.warning(
                "Circuit breaker OPEN. Pausing all API requests for %.0f seconds",
                cooldown
            )
            if self._on_rate_limit_callback:
                try:
                    self._on_rate_limit_callback()
                except (TypeError, ValueError, RuntimeError) as e:
                    _LOGGER.warning("Rate limit callback failed: %s", e)
            return cooldown
        return 0

    def record_success(self) -> None:
        """Record a successful request, resetting the circuit."""
        if self._consecutive_429s > 0:
            _LOGGER.debug("Circuit breaker reset after successful request")
        self._consecutive_429s = 0
        self._circuit_open_until = None

    def check(self) -> float:
        """Check if circuit is open.

        Returns:
            Seconds to wait if circuit is open, 0 if closed.
        """
        if self._circuit_open_until:
            remaining = (self._circuit_open_until - datetime.now()).total_seconds()
            if remaining > 0:
                return remaining
            # Circuit has closed naturally
            self._circuit_open_until = None
        return 0

    @property
    def is_open(self) -> bool:
        """Return True if circuit is currently open."""
        return self.check() > 0

    @property
    def consecutive_429s(self) -> int:
        """Return count of consecutive 429 errors."""
        return self._consecutive_429s


class RequestThrottler:
    """Enforces minimum delay between API requests to prevent bursts."""

    def __init__(self, min_delay: float = DEFAULT_MIN_REQUEST_DELAY) -> None:
        """Initialize the throttler.

        Args:
            min_delay: Minimum seconds between requests.
        """
        self._min_delay = min_delay
        self._last_request: float = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until minimum delay has passed since last request."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._min_delay and self._last_request > 0:
                wait_time = self._min_delay - elapsed
                _LOGGER.debug("Throttling: waiting %.2fs before next request", wait_time)
                await asyncio.sleep(wait_time)
            self._last_request = time.monotonic()


class IntuisAPI:
    """Minimal client wrapping the Intuis Netatmo endpoints."""

    def __init__(
            self,
            session: aiohttp.ClientSession,
            home_id: str | None = None,
            debug: bool = False,
            rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY,
            circuit_threshold: int = DEFAULT_CIRCUIT_THRESHOLD,
            min_request_delay: float = DEFAULT_MIN_REQUEST_DELAY,
    ) -> None:
        """Initialize the API client.

        Args:
            session: aiohttp client session.
            home_id: Optional home ID to use.
            debug: Enable debug logging.
            rate_limit_delay: Initial delay in seconds when rate limited.
            circuit_threshold: Number of 429s before circuit breaker opens.
            min_request_delay: Minimum seconds between requests.
        """
        self._session = session
        self._base_url: str = BASE_URLS[0]
        self.home_id: str | None = home_id
        self.home_timezone: str = "GMT"
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expiry: float | None = None
        self._debug: bool = debug

        # Rate limiting configuration
        self._rate_limit_delay = rate_limit_delay
        self._circuit_breaker = RateLimitCircuitBreaker(
            threshold=circuit_threshold,
            base_cooldown=30.0,
            max_cooldown=120.0,
        )
        self._throttler = RequestThrottler(min_delay=min_request_delay)

        _LOGGER.debug(
            "IntuisAPI initialized with home_id=%s, rate_limit_delay=%.1fs, "
            "circuit_threshold=%d, min_request_delay=%.2fs",
            home_id, rate_limit_delay, circuit_threshold, min_request_delay
        )

    @property
    def refresh_token(self) -> str | None:
        """Return the current refresh token."""
        return self._refresh_token

    @refresh_token.setter
    def refresh_token(self, value: str) -> None:
        """Set the refresh token."""
        self._refresh_token = value

    @property
    def circuit_breaker(self) -> RateLimitCircuitBreaker:
        """Return the circuit breaker instance."""
        return self._circuit_breaker

    def set_rate_limit_callback(self, callback: Callable[[], None]) -> None:
        """Set callback to invoke when rate limited."""
        self._circuit_breaker.set_rate_limit_callback(callback)

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
            self, method: str, path: str, retry: bool = True,
            full_url: str | None = None, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Make a request with rate limiting, circuit breaker, and retry logic.

        Rate Limit Handling:
        - Circuit breaker: If open, waits until cooldown expires
        - Throttler: Ensures minimum delay between requests
        - 429 responses: Uses Retry-After header or configured delay
        - Separate retry counts for 429 vs 5xx errors

        Retries:
        - 429 rate limits: up to RATE_LIMIT_ATTEMPTS with configured delay
        - HTTP 5xx errors: up to 3 attempts with exponential backoff
        - Network errors: up to 3 attempts with exponential backoff
        - HTTP 401: single token refresh then one retry

        Args:
            method: HTTP method (get, post, etc.)
            path: API path (appended to base_url unless full_url is provided)
            retry: Whether to retry on 401 after token refresh
            full_url: Optional full URL to use instead of base_url + path
        """
        # Check circuit breaker first
        wait_time = self._circuit_breaker.check()
        if wait_time > 0:
            _LOGGER.warning(
                "Circuit breaker open. Waiting %.0f seconds before request to %s",
                wait_time, path
            )
            await asyncio.sleep(wait_time)

        # Apply request throttling
        await self._throttler.acquire()

        await self._ensure_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"

        url = full_url if full_url else f"{self._base_url}{path}"
        if self._debug:
            _LOGGER.debug("Making API request: %s %s", method, url)

        # Default timeout if not provided
        timeout = kwargs.pop("timeout", 20)

        # Separate attempt counters for different error types
        server_attempts = 3
        rate_limit_attempts = DEFAULT_RATE_LIMIT_ATTEMPTS
        server_delay = 1.5
        rate_limit_delay = self._rate_limit_delay
        last_exc: Exception | None = None

        total_attempts = max(server_attempts, rate_limit_attempts)

        for attempt in range(1, total_attempts + 1):
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

                # Handle rate limiting (429) separately
                if resp.status == 429:
                    self._circuit_breaker.record_429()

                    if attempt < rate_limit_attempts:
                        # Check for Retry-After header
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = min(float(retry_after), DEFAULT_RATE_LIMIT_MAX_DELAY)
                            except ValueError:
                                delay = rate_limit_delay
                        else:
                            # Exponential backoff with configured base
                            delay = min(
                                rate_limit_delay * (2 ** (attempt - 1)),
                                DEFAULT_RATE_LIMIT_MAX_DELAY
                            )

                        _LOGGER.warning(
                            "Rate limited (429) for %s %s (attempt %s/%s). "
                            "Waiting %.1fs before retry",
                            method, path, attempt, rate_limit_attempts, delay
                        )
                        try:
                            await resp.release()
                        finally:
                            await asyncio.sleep(delay)
                        continue

                    # No more rate limit retries
                    _LOGGER.error(
                        "Rate limit exceeded for %s after %s attempts",
                        path, attempt
                    )
                    raise RateLimitError(f"Rate limited for {path} after {attempt} attempts")

                # Handle server errors (5xx)
                if 500 <= resp.status < 600:
                    if attempt < server_attempts:
                        _LOGGER.warning(
                            "Server error %s for %s %s (attempt %s/%s). Retrying in %.1fs",
                            resp.status, method, path, attempt, server_attempts, server_delay
                        )
                        try:
                            await resp.release()
                        finally:
                            await asyncio.sleep(server_delay)
                            server_delay *= 2
                        continue
                    # No more server error retries
                    resp.raise_for_status()

                # Success - record it and return
                resp.raise_for_status()
                self._circuit_breaker.record_success()
                return resp

            except aiohttp.ClientResponseError as e:
                # Non-retriable client errors (4xx other than 429/401)
                _LOGGER.error("API request failed for %s: %s", path, e)
                raise APIError(f"Request failed for {path}: {e.status}") from e
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exc = e
                if attempt < server_attempts:
                    _LOGGER.warning(
                        "Network error on %s %s (attempt %s/%s): %s. Retrying in %.1fs",
                        method, path, attempt, server_attempts, repr(e), server_delay
                    )
                    await asyncio.sleep(server_delay)
                    server_delay *= 2
                    continue
                _LOGGER.error(
                    "Cannot connect to API for %s after %s attempts: %s",
                    path, server_attempts, e
                )
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
            # Mask token for security - only show last 4 chars
            masked_token = f"***{self._refresh_token[-4:]}" if self._refresh_token else "None"
            _LOGGER.debug("Refreshing access token using refresh_token=%s", masked_token)
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
        elif mode in ("away", "boost", "hg"):
            # These modes may also accept temperature and duration
            if temp is not None:
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
            except (APIError, CannotConnect, RateLimitError, aiohttp.ClientError, asyncio.TimeoutError) as e:
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

            # Always log raw response structure at DEBUG level for diagnostics
            _LOGGER.debug(
                "Room %s energy response (scale=%s, types=%d): body has %d entries",
                room_id,
                scale,
                len(ENERGY_MEASURE_TYPES.split(",")),
                len(data.get("body", [])),
            )
            if self._debug:
                _LOGGER.debug("Room %s full energy response: %s", room_id, data)

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

    async def async_get_room_energy_daily(
        self, room_id: str, date_begin: int, date_end: int
    ) -> list[tuple[int, float]]:
        """Get daily energy consumption for a room over a date range.

        This method fetches energy data in bulk (one API call for the entire range)
        and returns individual daily values, significantly reducing API calls needed
        for historical imports.

        Args:
            room_id: The room ID.
            date_begin: Unix epoch timestamp for start of period.
            date_end: Unix epoch timestamp for end of period.

        Returns:
            List of tuples (timestamp, energy_wh) for each day in the range.
            Empty list on error.
        """
        form_data = {
            "home_id": self.home_id,
            "room_id": room_id,
            "scale": "1day",
            "type": ENERGY_MEASURE_TYPES,
            "date_begin": str(date_begin),
            "date_end": str(date_end),
        }

        try:
            async with await self._async_request(
                "post",
                ROOMMEASURE_PATH,
                data=form_data,
            ) as resp:
                data = await resp.json()

            if self._debug:
                _LOGGER.debug("Room %s daily energy response: %s", room_id, data)

            # Response format: {"body": [{"beg_time": ts, "step_time": 86400, "value": [[...], [...], ...]}, ...]}
            # Each inner array in "value" represents one day's energy
            daily_values: list[tuple[int, float]] = []
            body = data.get("body", [])

            for measure in body:
                beg_time = measure.get("beg_time", 0)
                step_time = measure.get("step_time", 86400)  # Default 1 day in seconds
                values = measure.get("value", [])

                for i, val_set in enumerate(values):
                    # Calculate timestamp for this day
                    day_ts = beg_time + (i * step_time)

                    # Sum all tariff values for this day
                    day_energy = 0.0
                    for val in val_set:
                        if val is not None:
                            day_energy += float(val)

                    daily_values.append((day_ts, day_energy))

            _LOGGER.debug(
                "Room %s: fetched %d daily values from %s to %s",
                room_id,
                len(daily_values),
                date_begin,
                date_end,
            )

            return daily_values

        except (APIError, KeyError, ValueError, TypeError) as e:
            _LOGGER.warning(
                "Daily energy request failed for room %s: %s",
                room_id,
                e,
                exc_info=True,
            )
            return []

    async def async_get_schedule(
            self, home_id: str, schedule_id: int
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch the full timetable for a given schedule.

        Returns a dict { room_id: [ { id, start, end, temp }, … ], … }.
        """
        url = f"{ENERGY_BASE}{GET_SCHEDULE_PATH}?home_id={home_id}&schedule_id={schedule_id}"
        async with await self._async_request(
            "get", GET_SCHEDULE_PATH, full_url=url, timeout=10
        ) as resp:
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
        async with await self._async_request(
            "post", SET_SCHEDULE_PATH, full_url=url, json=payload, timeout=10
        ) as resp:
            pass  # Success if no exception raised

    async def async_delete_schedule_slot(self, home_id: str, slot_id: str) -> None:
        """Delete a specific schedule slot by its ID."""
        url = f"{ENERGY_BASE}{DELETE_SCHEDULE_PATH}?home_id={home_id}&slot_id={slot_id}"
        async with await self._async_request(
            "delete", DELETE_SCHEDULE_PATH, full_url=url, timeout=10
        ) as resp:
            pass  # Success if no exception raised

    async def async_switch_schedule(self, home_id: str, schedule_id: int) -> None:
        """Switch the active weekly schedule."""
        payload = {"home_id": home_id, "schedule_id": schedule_id}
        url = f"{ENERGY_BASE}{SWITCH_SCHEDULE_PATH}"
        async with await self._async_request(
            "post", SWITCH_SCHEDULE_PATH, full_url=url, json=payload, timeout=10
        ) as resp:
            pass  # Success if no exception raised

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

        _LOGGER.debug("Sync schedule payload: %s", payload)

        async with await self._async_request(
            "post",
            SYNCHOMESCHEDULE_PATH,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=20,
        ) as resp:
            result = await resp.json()
            _LOGGER.debug("Sync schedule response (status=%s): %s", resp.status, result)

            # Check for API error in response body
            if "error" in result:
                error = result["error"]
                raise APIError(
                    f"sync_schedule failed: {error.get('message', 'Unknown error')} "
                    f"(code: {error.get('code')})"
                )

        _LOGGER.info("Schedule %s synced successfully", schedule_name)
