"""One shared source of heating intentions, separate from displayed cloud state."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import time
from typing import TYPE_CHECKING, TypedDict

from .utils.const import API_MODE_HOME, API_MODE_OFF

if TYPE_CHECKING:
    from .intuis_api.api import IntuisAPI


class OverrideIntent(TypedDict, total=False):
    """Existing persisted shape; optional keys allow legacy partial records."""

    mode: str
    temp: float | None
    end: int
    sticky: bool
    last_reapply: int


OverrideState = dict[str, OverrideIntent]


class OverrideManager:
    """Preserve the existing storage dictionary and serialize each room's commands."""

    def __init__(
        self,
        overrides: OverrideState | None = None,
        save_callback: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.overrides = overrides if overrides is not None else {}
        self._save_callback = save_callback
        self._locks: dict[str, asyncio.Lock] = {}
        self._save_lock = asyncio.Lock()

    def room_lock(self, room_id: str) -> asyncio.Lock:
        return self._locks.setdefault(room_id, asyncio.Lock())

    async def async_save(self) -> None:
        if self._save_callback is not None:
            async with self._save_lock:
                await self._save_callback()

    def discard(self, room_id: str, expected: OverrideIntent | None = None) -> bool:
        """An expired snapshot must never delete a newer command after an await."""
        if room_id not in self.overrides:
            return False
        if expected is not None and self.overrides[room_id] is not expected:
            return False
        del self.overrides[room_id]
        return True

    def record(
        self, room_id: str, mode: str, temp: float, duration: int
    ) -> OverrideIntent:
        now = int(time.time())
        intent: OverrideIntent = {
            "mode": mode,
            "temp": float(temp),
            "end": now + duration * 60,
            "sticky": True,
            "last_reapply": now,
        }
        self.overrides[room_id] = intent
        return intent

    async def async_command(
        self,
        api: IntuisAPI,
        room_id: str,
        mode: str,
        temp: float | None = None,
        duration: int | None = None,
        on_success: Callable[[OverrideIntent | None], None] | None = None,
    ) -> None:
        """Record only accepted commands; retain them if disk persistence fails.

        on_success publishes the bounded pending state before awaiting disk I/O,
        because a storage failure does not mean the equipment command was refused.
        """
        if mode not in (API_MODE_HOME, API_MODE_OFF) and (
            temp is None or duration is None
        ):
            raise ValueError(
                "A timed heating command requires temperature and duration"
            )
        async with self.room_lock(room_id):
            if mode in (API_MODE_HOME, API_MODE_OFF):
                await api.async_set_room_state(room_id, mode)
                changed = self.discard(room_id)
                intent = None
            else:
                await api.async_set_room_state(room_id, mode, temp, duration)
                intent = self.record(room_id, mode, temp, duration)
                changed = True
            if on_success is not None:
                on_success(intent)
            if changed:
                await self.async_save()

    async def async_reapply(
        self,
        api: IntuisAPI,
        room_id: str,
        expected: OverrideIntent,
        duration: int,
    ) -> bool:
        """Reapply only if a concurrent user command has not replaced the intent."""
        async with self.room_lock(room_id):
            if self.overrides.get(room_id) is not expected:
                return False
            await api.async_set_room_state(
                room_id,
                expected["mode"],
                float(expected["temp"]) if expected.get("temp") is not None else None,
                duration,
            )
            now = int(time.time())
            expected.update(end=now + duration * 60, last_reapply=now)
            return True
