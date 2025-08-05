from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class IntuisModule:
    """Base class for modules in the Intuis Connect integration."""

    def __init__(self, module_id: str, module_type: str):
        """Initialize the Intuis module."""
        self.id = module_id
        self.type = module_type

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntuisModule:
        """Initialize the module from a dictionary."""
        module_type = data.get("type")
        if module_type is None:
            raise ValueError("Module type is required")
        if module_type == "NMR":
            return NMRIntuisModule.from_dict(data)
        if module_type == "NMG":
            return NMGIntuisModule.from_dict(data)
        if module_type == "NMH":
            return NMHIntuisModule.from_dict(data)
        raise ValueError(f"Unknown module type: {module_type}")


class NMRIntuisModule(IntuisModule):
    """Class to represent a NMR module in the Intuis Connect system."""

    def __init__(
            self,
            module_id: str,
            firmware_revision: int,
            last_seen: int,
            bridge: str,
            hardware_version: int | None = None,
            image_type: int | None = None,
            manufacturer_id: int | None = None,
    ) -> None:
        """Initialize the NMR module."""
        IntuisModule.__init__(self, module_id, "NMR")
        self.firmware_revision = firmware_revision
        self.last_seen = last_seen
        self.bridge = bridge
        self.hardware_version = hardware_version
        self.image_type = image_type
        self.manufacturer_id = manufacturer_id

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NMRIntuisModule:
        """Create a NMR module from a dictionary."""
        return NMRIntuisModule(
            module_id=data["id"],
            firmware_revision=data["firmware_revision"],
            last_seen=data["last_seen"],
            bridge=data["bridge"],
            hardware_version=data.get("hardware_version"),
            image_type=data.get("image_type"),
            manufacturer_id=data.get("manufacturer_id"),
        )


class NMGIntuisModule(IntuisModule):
    """Class to represent a NMG module in the Intuis Connect system."""

    def __init__(
            self,
            module_id: str,
            firmware_revision: int,
            hardware_version: int,
            uptime: int,
            wifi_strength: int,
            subtype: str,
            configure: bool,
            debug_enabled: bool,
            install_progress: int,
            open_zigbee: bool,
            outdoor_temperature: float,
            router_id: str,
            therm_setpoint_day_color_type: str,
            therm_setpoint_default_duration: int,
    ) -> None:
        """Initialize the NMG module."""
        IntuisModule.__init__(self, module_id, "NMG")
        self.firmware_revision = firmware_revision
        self.hardware_version = hardware_version
        self.uptime = uptime
        self.wifi_strength = wifi_strength
        self.subtype = subtype
        self.configure = configure
        self.debug_enabled = debug_enabled
        self.install_progress = install_progress
        self.open_zigbee = open_zigbee
        self.outdoor_temperature = outdoor_temperature
        self.router_id = router_id
        self.therm_setpoint_day_color_type = therm_setpoint_day_color_type
        self.therm_setpoint_default_duration = therm_setpoint_default_duration

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NMGIntuisModule:
        """Create a NMG module from a dictionary."""
        return NMGIntuisModule(
            module_id=data["id"],
            firmware_revision=data["firmware_revision"],
            hardware_version=data["hardware_version"],
            uptime=data["uptime"],
            wifi_strength=data["wifi_strength"],
            subtype=data["subtype"],
            configure=data["configure"],
            debug_enabled=data["debug_enabled"],
            install_progress=data["install_progress"],
            open_zigbee=data["open_zigbee"],
            outdoor_temperature=data["outdoor_temperature"],
            router_id=data["router_id"],
            therm_setpoint_day_color_type=data["therm_setpoint_day_color_type"],
            therm_setpoint_default_duration=data["therm_setpoint_default_duration"],
        )


class NMHIntuisModule(IntuisModule):
    """Class to represent a NMH module in the Intuis Connect system."""

    def __init__(
            self,
            module_id: str,
            last_seen: int,
            bridge: str,
            firmware_revision_thirdparty: str,
            muller_type: str,
            offload: bool,
            presence_sensor: str,
            radiator_state: str,
            reachable: bool,
            router_id: str,
    ) -> None:
        """Initialize the NMH module."""
        IntuisModule.__init__(self, module_id, "NMH")
        self.last_seen = last_seen
        self.bridge = bridge
        self.firmware_revision_thirdparty = firmware_revision_thirdparty
        self.muller_type = muller_type
        self.offload = offload
        self.presence_sensor = presence_sensor
        self.radiator_state = radiator_state
        self.reachable = reachable
        self.router_id = router_id

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NMHIntuisModule:
        """Create a NMH module from a dictionary."""
        return NMHIntuisModule(
            module_id=data["id"],
            last_seen=data["last_seen"],
            bridge=data["bridge"],
            firmware_revision_thirdparty=data["firmware_revision_thirdparty"],
            muller_type=data["muller_type"],
            offload=data["offload"],
            presence_sensor=data["presence_sensor"],
            radiator_state=data["radiator_state"],
            reachable=data["reachable"],
            router_id=data["router_id"],
        )
