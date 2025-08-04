"""Binary sensors (presence, window, anticipation)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import IntuisDataUpdateCoordinator
from .device import build_device_info
from .helper import get_basic_utils


class _Base(CoordinatorEntity[IntuisDataUpdateCoordinator], BinarySensorEntity):
    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            room_id: str,
            room_name: str,
            name: str,
            uid: str,
            device_class: BinarySensorDeviceClass,
    ) -> None:
        super().__init__(coordinator)
        self._room_id = room_id
        self._attr_name = name
        self._attr_unique_id = uid
        self._attr_device_class = device_class
        self._dev = build_device_info(home_id, room_id, room_name)

    @property
    def device_info(self):
        return self._dev


class PresenceSensor(_Base):
    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            h: str,
            r: str,
            n: str,
    ) -> None:
        super().__init__(
            coordinator, h, r, n, f"{n} Presence", f"{r}_presence", BinarySensorDeviceClass.MOTION
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.data["rooms"][self._room_id]["presence"]


class WindowSensor(_Base):
    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            h: str,
            r: str,
            n: str,
    ) -> None:
        super().__init__(
            coordinator, h, r, n, f"{n} Open Window", f"{r}_window", BinarySensorDeviceClass.WINDOW
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.data["rooms"][self._room_id]["open_window"]


class AnticipationSensor(_Base):
    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            h: str,
            r: str,
            n: str,
    ) -> None:
        super().__init__(
            coordinator,
            h,
            r,
            n,
            f"{n} Anticipation",
            f"{r}_anticipation",
            BinarySensorDeviceClass.HEAT,
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.data["rooms"][self._room_id]["anticipation"]


class BoostStatusSensor(_Base):
    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            h: str,
            r: str,
            n: str,
    ) -> None:
        super().__init__(
            coordinator,
            h,
            r,
            n,
            f"{n} Boost Status",
            f"{r}_boost_status",
            BinarySensorDeviceClass.HEAT,
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.data["rooms"][self._room_id]["boost_status"] != "disabled"


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator, home_id, rooms, api = get_basic_utils(hass, entry)

    ent: list[BinarySensorEntity] = []
    for room_id, room in rooms:
        ent.extend(
            [
                PresenceSensor(coordinator, home_id, room_id, room.name),
                WindowSensor(coordinator, home_id, room_id, room.name),
                AnticipationSensor(coordinator, home_id, room_id, room.name),
            ]
        )
    async_add_entities(ent)
