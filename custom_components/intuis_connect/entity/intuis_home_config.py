from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

class IntuisHomeConfig:
    """Class to represent the Intuis home configuration."""

    def __init__(self, home_id: str, absence_detection: str, anticipation: bool, balancing: bool,
                 debug_enabled: bool, offload: bool, open_window: bool,
                 presence_threshold: int, schedule_optimization: bool, temp_lowering_mode: str,
                 therm_setpoint_day_color_red_ejp_offset: int, therm_setpoint_day_color_red_ejp_type: str,
                 therm_setpoint_day_color_white_offset: int, therm_setpoint_day_color_white_type: str,
                 therm_setpoint_default_duration: int, unit_temperature: int, timezone: str, module_id: str) -> None:
        """Initialize the Intuis home configuration."""
        self.home_id = home_id
        self.absence_detection = absence_detection
        self.anticipation = anticipation
        self.balancing = balancing
        self.debug_enabled = debug_enabled
        self.offload = offload
        self.open_window = open_window
        self.presence_threshold = presence_threshold
        self.schedule_optimization = schedule_optimization
        self.temp_lowering_mode = temp_lowering_mode
        self.therm_setpoint_day_color_red_ejp_offset = therm_setpoint_day_color_red_ejp_offset
        self.therm_setpoint_day_color_red_ejp_type = therm_setpoint_day_color_red_ejp_type
        self.therm_setpoint_day_color_white_offset = therm_setpoint_day_color_white_offset
        self.therm_setpoint_day_color_white_type = therm_setpoint_day_color_white_type
        self.therm_setpoint_default_duration = therm_setpoint_default_duration
        self.unit_temperature = unit_temperature
        self.timezone = timezone
        self.module_id = module_id

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntuisHomeConfig:
        """Create an Intuis home configuration from a dictionary."""

        modules: dict[str, Any] | None = data.get("modules", None)
        if not modules:
            raise ValueError("No modules found in the configuration data")

        if not isinstance(modules, list):
            raise ValueError("Modules data should be a list")
        
        if len(modules) != 1:
            raise ValueError("Expected exactly one module in the configuration data")
        
        module = modules[0]

        home_config = cls(
            home_id=data.get("home_id"),
            absence_detection=module.get("absence_detection", "notify"),
            anticipation=module.get("anticipation"),
            balancing=module.get("balancing"),
            debug_enabled=module.get("debug_enabled"),
            module_id=module.get("id"),
            offload=module.get("offload"),
            open_window=module.get("open_window"),
            presence_threshold=module.get("presence_threshold"),
            schedule_optimization=module.get("schedule_optimization"),
            temp_lowering_mode=module.get("temp_lowering_mode"),
            therm_setpoint_day_color_red_ejp_offset=module.get("therm_setpoint_day_color_red_ejp_offset"),
            therm_setpoint_day_color_red_ejp_type= module.get("therm_setpoint_day_color_red_ejp_type"),
            therm_setpoint_day_color_white_offset=module.get("therm_setpoint_day_color_white_offset"),
            therm_setpoint_day_color_white_type=module.get("therm_setpoint_day_color_white_type"),
            therm_setpoint_default_duration=module.get("therm_setpoint_default_duration"),
            unit_temperature=module.get("unit_temperature"),
            timezone=data.get("timezone")
        )

        _LOGGER.debug("Created IntuisHomeConfig: %s", home_config)
        return home_config