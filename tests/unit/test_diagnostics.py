"""Support exports expose useful structure without copying account/cloud data."""

from datetime import timedelta
import json
from types import SimpleNamespace

from custom_components.intuis_connect.diagnostics import async_get_config_entry_diagnostics
from custom_components.intuis_connect.history_import import HistoryImportManager
from custom_components.intuis_connect.utils.const import DOMAIN


async def test_diagnostics_anonymizes_rooms_and_excludes_entry_and_exception_text(ha_hass):
    private = "SENSITIVE-ACCOUNT-ROOM-HOME-TOKEN"
    entry = SimpleNamespace(entry_id=private, version=1, data={"refresh_token": private},
                            title=private, options={"price_entity": private})
    room = SimpleNamespace(name=private, temperature=20, target_temperature=21,
                           mode="manual", energy=1.5, modules=[private])
    manager = HistoryImportManager(ha_hass, private)
    manager.status = "partial"
    manager.last_error = private
    manager.current_room = private
    manager.daily_diagnostics = {private: {
        "status": "failed", "failed_stage": "fetch", "error_type": "CannotConnect",
        "requested_days": 2, "received_samples": 0, "imported_days": 0,
    }}
    ha_hass.data[DOMAIN] = {
        private: {
            "intuis_home": SimpleNamespace(id=private, name=private, city=private,
                coordinates=[private], rooms={private: room}, schedules=[
                    SimpleNamespace(id=private, name=private, selected=True, zones=[private],
                                    timetables=[private])]),
            "coordinator": SimpleNamespace(data={"rooms": {private: room}},
                last_update_success=True, update_interval=timedelta(minutes=5)),
        },
        "import_managers": {private: manager},
    }
    result = await async_get_config_entry_diagnostics(ha_hass, entry)
    assert private not in json.dumps(result)
    assert list(result["rooms"]) == ["room_1"]
    assert result["history_import"]["last_daily_run"]["room_1"]["failed_stage"] == "fetch"
    assert result["coordinator"]["update_interval_seconds"] == 300
    assert result["rooms"]["room_1"]["temperature"] == 20
    result["history_import"]["last_daily_run"]["room_1"]["status"] = "changed"
    assert manager.daily_diagnostics[private]["status"] == "failed"


async def test_diagnostics_unloaded_entry_is_safe(ha_hass):
    result = await async_get_config_entry_diagnostics(
        ha_hass, SimpleNamespace(entry_id="missing", version=1)
    )
    assert result["rooms"] == {}
    assert result["history_import"]["status"] == "not_started"
    assert result["coordinator"]["last_update_success"] is None
