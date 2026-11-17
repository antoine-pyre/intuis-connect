"""External statistics contracts, adapted from TheFab21's hourly/cost proposals.

Source: https://github.com/antoine-pyre/intuis-connect/pull/22
External series deliberately do not replace daily recorder sensor statistics.
"""
from __future__ import annotations

import hashlib
import json
import typing

from homeassistant.components.recorder import models
from homeassistant.components.recorder.models import StatisticMetaData

from .utils.const import DOMAIN


def statistic_id(home_id: str, room_id: str | None, kind: str = "energy") -> str:
    """Stable identity independent of entity IDs and labels, including home totals."""
    if kind not in ("energy", "cost"):
        raise ValueError("Unsupported external statistics kind")
    identity = json.dumps([home_id, room_id], ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(identity.encode()).hexdigest()[:32]
    return f"{DOMAIN}:{kind}_{digest}"


def _supported_meta_keys() -> frozenset[str]:
    """Keys this recorder's StatisticMetaData declares.

    mean_type and unit_class arrived in separate schema versions, so neither
    may stand in for the other: gating unit_class on StatisticMeanType left
    the column unset, and the energy dashboard only lists statistics whose
    unit_class is exactly "energy".
    """
    try:
        return frozenset(typing.get_type_hints(StatisticMetaData))
    except Exception:  # pragma: no cover - a recorder we cannot introspect
        return frozenset({"has_mean", "has_sum", "name", "source",
                          "statistic_id", "unit_of_measurement"})


def metadata(home_id, room_id, name, *, kind="energy", currency="EUR"):
    """Build the native metadata format for both supported recorder versions."""
    candidate = {
        "source": DOMAIN,
        "statistic_id": statistic_id(home_id, room_id, kind),
        "name": name,
        "has_mean": False,
        "has_sum": True,
        "unit_of_measurement": "kWh" if kind == "energy" else currency,
        "unit_class": "energy" if kind == "energy" else None,
    }
    if hasattr(models, "StatisticMeanType"):
        candidate["mean_type"] = models.StatisticMeanType.NONE
    supported = _supported_meta_keys()
    return {key: value for key, value in candidate.items() if key in supported}
