"""Resolve domain services against currently loaded homes, never cached choices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .utils.const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def target_entries(
    hass: HomeAssistant, home_id: str | None = None
) -> list[tuple[str, dict[str, Any]]]:
    """Take a stable snapshot, excluding domain-level bookkeeping dictionaries."""
    entries = []
    for entry_id, data in list(hass.data.get(DOMAIN, {}).items()):
        if (
            not isinstance(data, dict)
            or not data.get("intuis_home")
            or not data.get("api")
        ):
            continue
        if home_id is None or data["intuis_home"].id == home_id:
            entries.append((entry_id, data))
    return entries


def require_targets(
    hass: HomeAssistant, home_id: str | None
) -> list[tuple[str, dict[str, Any]]]:
    entries = target_entries(hass, home_id)
    if not entries:
        raise ServiceValidationError(
            f"Home {home_id} is not loaded"
            if home_id
            else "No configured home is loaded"
        )
    return entries


def first_target(
    hass: HomeAssistant, home_id: str | None
) -> tuple[str, dict[str, Any]]:
    entries = require_targets(hass, home_id)
    if len(entries) > 1 and home_id is None:
        _LOGGER.warning(
            "Multiple homes configured; using first home. Specify home_id to select a home."
        )
    return entries[0]


def is_loaded(hass: HomeAssistant, entry_id: str, data: dict[str, Any]) -> bool:
    """An unloaded/reloaded entry's old model must not receive a late response."""
    return hass.data.get(DOMAIN, {}).get(entry_id) is data
