"""External statistics contracts, adapted from TheFab21's hourly/cost proposals.

Source: https://github.com/antoine-pyre/intuis-connect/pull/22
External series deliberately do not replace daily recorder sensor statistics.
"""
from __future__ import annotations

import hashlib
import json

from homeassistant.components.recorder import models

from .utils.const import DOMAIN


def statistic_id(home_id: str, room_id: str | None, kind: str = "energy") -> str:
    """Stable identity independent of entity IDs and labels, including home totals."""
    if kind not in ("energy", "cost"):
        raise ValueError("Unsupported external statistics kind")
    identity = json.dumps([home_id, room_id], ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(identity.encode()).hexdigest()[:32]
    return f"{DOMAIN}:{kind}_{digest}"


def metadata(home_id, room_id, name, *, kind="energy", currency="EUR"):
    """Build the native metadata format for both supported recorder versions."""
    result = {
        "source": DOMAIN,
        "statistic_id": statistic_id(home_id, room_id, kind),
        "name": name,
        "has_sum": True,
        "unit_of_measurement": "kWh" if kind == "energy" else currency,
    }
    if hasattr(models, "StatisticMeanType"):
        result.update(mean_type=models.StatisticMeanType.NONE,
                      unit_class="energy" if kind == "energy" else None)
    else:
        result["has_mean"] = False
    return result
