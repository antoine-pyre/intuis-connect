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
from .data import IntuisRoom
from .device import build_device_info
from .entity import IntuisEntity
from .helper import get_basic_utils, get_room


class _Base(CoordinatorEntity[IntuisDataUpdateCoordinator], BinarySensorEntity, IntuisEntity):
    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            room: IntuisRoom,
            name: str,
            uid: str,
            device_class: BinarySensorDeviceClass,
    ) -> None:
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._attr_name = name
        self._attr_unique_id = uid
        self._attr_device_class = device_class
        self._dev = build_device_info(home_id, room.id, room.name)

    @property
    def device_info(self):
        return self._dev


class PresenceSensor(_Base):
    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            h: str,
            r: IntuisRoom,
    ) -> None:
        super().__init__(
            coordinator, h, r, f"{r.name} Presence", f"{r.id}_presence", BinarySensorDeviceClass.MOTION
        )

    @property
    def is_on(self) -> bool:
        return self._get_room().presence


class WindowSensor(_Base):
    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            h: str,
            r: IntuisRoom,
    ) -> None:
        super().__init__(
            coordinator, h, r, f"{r.name} Open Window", f"{r.id}_window", BinarySensorDeviceClass.WINDOW
        )

    @property
    def is_on(self) -> bool:
        return self._get_room().open_window


class AnticipationSensor(_Base):
    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            h: str,
            r: IntuisRoom,
    ) -> None:
        super().__init__(
            coordinator,
            h,
            r,
            f"{r.name} Anticipation",
            f"{r.id}_anticipation",
            BinarySensorDeviceClass.HEAT,
        )

    @property
    def is_on(self) -> bool:
        return self._get_room().anticipation


class BoostStatusSensor(_Base):
    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            h: str,
            r: IntuisRoom
    ) -> None:
        super().__init__(
            coordinator,
            h,
            r,
            f"{r.name} Boost Status",
            f"{r.id}_boost_status",
            BinarySensorDeviceClass.HEAT,
        )

    @property
    def is_on(self) -> bool:
        return self._get_room().boost_status != "disabled"


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator, home_id, rooms, api = get_basic_utils(hass, entry)

    ent: list[BinarySensorEntity] = []
    for room_id in rooms:
        room = rooms[room_id]
        ent.extend(
            [
                PresenceSensor(coordinator, home_id, room),
                WindowSensor(coordinator, home_id, room),
                AnticipationSensor(coordinator, home_id, room),
            ]
        )
    async_add_entities(ent)
