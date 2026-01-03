"""Binary sensors (presence, window, anticipation, module health)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity.intuis_entity import IntuisDataUpdateCoordinator, IntuisEntity
from .entity.intuis_module import NMHIntuisModule
from .entity.intuis_room import IntuisRoom
from .utils.helper import get_basic_utils


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
        self._attr_entity_registry_enabled_default = False


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


class ModuleReachableSensor(_Base):
    """Binary sensor for NMH module reachability."""

    def __init__(
            self,
            coordinator: IntuisDataUpdateCoordinator,
            home_id: str,
            room: IntuisRoom,
            module: NMHIntuisModule,
    ) -> None:
        self._module_id = module.id
        # Use short module ID (last 6 chars) for readability
        short_id = module.id[-6:] if len(module.id) > 6 else module.id
        super().__init__(
            coordinator,
            home_id,
            room,
            f"{room.name} {short_id} Reachable",
            f"module_{module.id}_reachable",
            BinarySensorDeviceClass.CONNECTIVITY,
        )
        # Enable by default for proactive alerts
        self._attr_entity_registry_enabled_default = True

    @property
    def is_on(self) -> bool:
        """Return True if module is reachable."""
        room = self._get_room()
        if not room or not room.modules:
            return False
        for module in room.modules:
            if isinstance(module, NMHIntuisModule) and module.id == self._module_id:
                return module.reachable
        return False


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
        # Add module reachability sensors for each NMH module
        for module in room.modules:
            if isinstance(module, NMHIntuisModule):
                ent.append(ModuleReachableSensor(coordinator, home_id, room, module))

    async_add_entities(ent, update_before_add=True)
