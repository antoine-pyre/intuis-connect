from __future__ import annotations

import logging
from typing import Any

from ..entity.intuis_module import IntuisModule, NMHIntuisModule

_LOGGER = logging.getLogger(__name__)


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

    def __init__(self, definition: IntuisRoomDefinition, id: str, name: str, mode: str, target_temperature: float,
                 temperature: float, presence: bool, open_window: bool, anticipation: bool,
                 muller_type: str, boost_status: str, modules: list[IntuisModule], therm_setpoint_end_time: int,
                 bridge_id: str | None = None, heating: bool = False) -> None:
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
        self.therm_setpoint_end_time = therm_setpoint_end_time
        self.bridge_id = bridge_id
        self.heating = heating
        # Accumulated counters (updated by mapper, not from API)
        self.minutes: int = 0
        self.energy: float = 0.0

    @staticmethod
    def from_dict(definition: IntuisRoomDefinition, data: dict[str, Any], modules: list[IntuisModule]) -> IntuisRoom:
        """Create a room from a dictionary and its definition."""

        # Filter modules based on the room definition
        filtered_modules = [module for module in modules if module.id in definition.module_ids]

        # Get bridge_id from the first module that has one
        bridge_id = None
        for module in filtered_modules:
            if hasattr(module, "bridge") and module.bridge:
                bridge_id = module.bridge
                break

        # Determine heating status from NMH modules' radiator_state
        # A room is heating if any of its NMH modules has radiator_state == "heating"
        # Also check if temperature is below target (heating should be active)
        heating = False
        target_temp = data.get("therm_setpoint_temperature", 0.0)
        current_temp = data.get("therm_measured_temperature", 0.0)
        
        # Log all NMH modules' radiator_state for debugging
        nmh_modules_found = []
        for module in filtered_modules:
            if isinstance(module, NMHIntuisModule):
                nmh_modules_found.append({
                    "id": module.id,
                    "radiator_state": module.radiator_state,
                    "reachable": module.reachable
                })
                # Check for "heating" state (case-insensitive)
                if module.radiator_state and module.radiator_state.lower() == "heating":
                    heating = True
                    _LOGGER.debug(
                        "Room %s: NMH module %s has radiator_state='heating'",
                        data["id"], module.id
                    )
                # Also check for "auto" state - if temp is below target, heating is likely active
                elif (module.radiator_state and module.radiator_state.lower() == "auto" 
                      and target_temp > 0 and current_temp < target_temp - 0.5):
                    heating = True
                    _LOGGER.debug(
                        "Room %s: NMH module %s has radiator_state='auto' and temp (%.1f) < target (%.1f) - assuming heating",
                        data["id"], module.id, current_temp, target_temp
                    )
        
        if nmh_modules_found:
            _LOGGER.debug(
                "Room %s: Found %d NMH module(s): %s. Heating detected: %s",
                data["id"], len(nmh_modules_found), nmh_modules_found, heating
            )
        else:
            _LOGGER.debug(
                "Room %s: No NMH modules found. Filtered modules: %s",
                data["id"], [m.id for m in filtered_modules]
            )
        
        # Fallback: if no NMH modules or radiator_state doesn't indicate heating,
        # check if temperature is below target (heating should be active)
        if not heating and target_temp > 0 and current_temp < target_temp - 0.5:
            # Temperature is significantly below target, likely heating
            _LOGGER.debug(
                "Room %s: No heating detected from radiator_state, but temp (%.1f) < target (%.1f) - assuming heating",
                data["id"], current_temp, target_temp
            )
            heating = True

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
            therm_setpoint_end_time=data.get("therm_setpoint_end_time", 0),
            modules=filtered_modules,
            bridge_id=bridge_id,
            heating=heating,
        )

    def __repr__(self) -> str:
        """Return a string representation of the room."""
        return f"IntuisRoom(definition={self.definition}, id={self.id}, name={self.name}, mode={self.mode}, target_temperature={self.target_temperature}, temperature={self.temperature}, heating={self.heating}, presence={self.presence}, open_window={self.open_window}, anticipation={self.anticipation}, muller_type={self.muller_type}, boost_status={self.boost_status}, modules={self.modules})"
