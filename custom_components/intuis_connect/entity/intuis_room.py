from __future__ import annotations

from typing import Any

from custom_components.intuis_connect.entity.intuis_module import IntuisModule


class IntuisRoomDefinition:
    """Class to define a room in the Intuis Connect system."""

    def __init__(self, id: str, name: str, type: str, module_ids: list[str] = None,
                 modules: list[dict[str, Any]] = None, therm_relay: dict[str, Any] = None) -> None:
        """Initialize the room definition."""
        self.id = id
        self.name = name
        self.type = type
        self.module_ids = module_ids or []
        self.modules = modules or []
        self.therm_relay = therm_relay

    def __repr__(self) -> str:
        """Return a string representation of the room."""
        return f"IntuisRoomDefinition(id={self.id}, name={self.name}, type={self.type}, module_ids={self.module_ids}, modules={self.modules}, therm_relay={self.therm_relay})"

    @staticmethod
    def from_dict(data: dict[str, Any]) -> IntuisRoomDefinition:
        """Create a room definition from a dictionary."""
        return IntuisRoomDefinition(
            id=data["id"],
            name=data["name"],
            type=data["type"],
            module_ids=data.get("module_ids", []),
            modules=data.get("modules", []),
            therm_relay=data.get("therm_relay")
        )


class IntuisRoom:
    """Class to represent a room in the Intuis Connect system."""

    heating: bool = False
    minutes: int = 0
    energy: float = 0.0

    def __init__(self, definition: IntuisRoomDefinition, id: str, name: str, mode: str, target_temperature: float,
                 temperature: float, presence: bool, open_window: bool, anticipation: bool,
                 muller_type: str, boost_status: str, modules: list[IntuisModule]) -> None:
        """Initialize the room with its definition."""
        self.definition = definition
        self.id = id
        self.name = name
        self.mode = mode
        self.target_temperature = target_temperature
        self.temperature = temperature
        self.presence = presence
        self.open_window = open_window
        self.anticipation = anticipation
        self.muller_type = muller_type
        self.boost_status = boost_status
        self.modules = modules

    @staticmethod
    def from_dict(definition: IntuisRoomDefinition, data: dict[str, Any], modules: list[IntuisModule]) -> IntuisRoom:
        """Create a room from a dictionary and its definition."""

        # Filter modules based on the room definition
        filtered_modules = [module for module in modules if module.id in definition.module_ids]

        return IntuisRoom(
            definition=definition,
            id=data["id"],
            name=definition.name,
            mode=data.get("therm_setpoint_mode", "unknown"),
            temperature=data.get("therm_measured_temperature", 0.0),
            target_temperature=data.get("therm_setpoint_temperature", 0.0),
            presence=data.get("presence", False),
            open_window=data.get("open_window", False),
            anticipation=data.get("anticipation", False),
            muller_type=data.get("muller_type", ""),
            boost_status=data.get("boost_status", "disabled"),
            modules=filtered_modules
        )

    def __repr__(self) -> str:
        """Return a string representation of the room."""
        return f"IntuisRoom(definition={self.definition}, id={self.id}, name={self.name}, mode={self.mode}, target_temperature={self.target_temperature}, temperature={self.temperature}, heating={self.heating}, presence={self.presence}, open_window={self.open_window}, anticipation={self.anticipation}, muller_type={self.muller_type}, boost_status={self.boost_status}, modules={self.modules})"
