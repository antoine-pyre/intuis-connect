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

from custom_components.intuis_connect.entity.intuis_entity import IntuisDataUpdateCoordinator, IntuisEntity
from custom_components.intuis_connect.entity.intuis_room import IntuisRoom
from custom_components.intuis_connect.helper import get_basic_utils


class _Base(CoordinatorEntity[IntuisDataUpdateCoordinator], BinarySensorEntity, IntuisEntity):
    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            room: IntuisRoom,
            name: str,
            metric: str,
            device_class: BinarySensorDeviceClass,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        BinarySensorEntity.__init__(self)
        IntuisEntity.__init__(self, coordinator, room, home_id, name, metric)
        self._attr_device_class = device_class


class PresenceSensor(_Base):
    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            h: str,
            r: IntuisRoom,
    ) -> None:
        super().__init__(
            coordinator, h, r, f"{r.name} Presence", "presence", BinarySensorDeviceClass.MOTION
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
            coordinator, h, r, f"{r.name} Open Window", "window", BinarySensorDeviceClass.WINDOW
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
            "anticipation",
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
            "boost_status",
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
    async_add_entities(ent, update_before_add=True)
