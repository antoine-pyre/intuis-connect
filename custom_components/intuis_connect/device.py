"""Device helper factory."""
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def build_device_info(home_id: str, room_id: str, room_name: str) -> DeviceInfo:
    """Return a consistent DeviceInfo for all entities of one room."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{home_id}_{room_id}")},
        name=room_name,
        manufacturer="Muller Intuitiv (Netatmo)",
        model="Electric Radiator",
        suggested_area=room_name,
    )
