"""Support exports expose useful structure without copying account/cloud data."""

from datetime import timedelta
import json
from types import SimpleNamespace

from custom_components.intuis_connect.diagnostics import async_get_config_entry_diagnostics
from custom_components.intuis_connect.entity.intuis_schedule import IntuisSchedule
from custom_components.intuis_connect.history_import import HistoryImportManager
from custom_components.intuis_connect.utils.const import DOMAIN


async def test_diagnostics_anonymizes_rooms_and_excludes_entry_and_exception_text(ha_hass):
    private = "SENSITIVE-ACCOUNT-ROOM-HOME-TOKEN"
    entry = SimpleNamespace(entry_id=private, version=1, data={"refresh_token": private},
                            title=private, options={"price_entity": private})
    room = SimpleNamespace(name="Salon", temperature=20, target_temperature=21,
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
                    SimpleNamespace(id=private, name="Semaine", selected=True, zones=[private],
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
    assert result["planning_export"]["schedules"] == []


async def test_diagnostics_exports_all_plannings_without_cloud_ids_or_mutation(ha_hass):
    raw = [
        {
            "id": "CLOUD-SCHEDULE-NORMAL", "type": "therm", "name": "Normal",
            "selected": True, "default": True, "away_temp": 12.5, "hg_temp": 7,
            "timetable": [{"m_offset": 0, "zone_id": 1}, {"m_offset": 360, "zone_id": 2},
                          {"m_offset": 10050, "zone_id": 1}],
            "zones": [
                {"id": 1, "name": "Nuit", "type": 1,
                 "rooms_temp": [{"room_id": "CLOUD-ROOM-SALON", "temp": 17.5}]},
                {"id": 2, "name": "Jour", "type": 8,
                 "rooms": [{"id": "CLOUD-ROOM-SALON", "therm_setpoint_temperature": 20.5},
                           {"id": "CLOUD-ROOM-FP", "therm_setpoint_fp": "comfort"}]},
                {"id": 3, "name": "Inutilisée", "type": 5,
                 "rooms_temp": [{"room_id": "CLOUD-ROOM-SALON", "temp": 16}]},
            ],
        },
        {
            "id": "CLOUD-SCHEDULE-ROUGE", "type": "therm", "name": "Rouge ",
            "selected": False, "timetable": [{"m_offset": 0, "zone_id": 4}],
            "zones": [{"id": 4, "name": "Jour rouge", "rooms_temp": [
                {"room_id": "CLOUD-ROOM-SALON", "temp": 15},
                {"room_id": "CLOUD-ROOM-ORPHAN", "temp": None},
            ], "rooms": [{"id": "CLOUD-ROOM-FP", "therm_setpoint_fp": "away"}]}],
        },
        {
            "id": "CLOUD-SCHEDULE-VALENTINE", "type": "therm", "name": "Normal Valentine",
            "selected": False, "timetable": [], "zones": [],
        },
        {
            "id": "CLOUD-SCHEDULE-TARIFF", "type": "electricity", "name": "Tarif",
            "selected": True, "tariff": "tempo", "tariff_option": "hc_hp",
            "power_threshold": 9, "contract_power_unit": "kVA", "version": 2,
            "timetable": [{"m_offset": 0, "zone_id": 0}],
            "zones": [{"id": 0, "price_type": "hc", "price": 0.1234}],
        },
        {
            "id": "CLOUD-SCHEDULE-EVENT", "type": "event", "name": "Eau chaude",
            "timetable": [{"m_offset": 60, "zone_id": 0}],
            "zones": [{"id": 0, "name": "Marche", "modules": [
                {"id": "CLOUD-MODULE", "dhw_state": "on", "token": "SECRET"}]},
                {"id": 1, "name": "Arrêt", "modules": [
                    {"id": "CLOUD-MODULE", "dhw_state": "off"}]}],
        },
    ]
    schedules = [IntuisSchedule.from_dict(s) for s in raw]
    home = SimpleNamespace(id="CLOUD-HOME", timezone="Europe/Paris", rooms={
        "CLOUD-ROOM-SALON": SimpleNamespace(name="Salon"),
        "CLOUD-ROOM-FP": SimpleNamespace(name="Entrée"),
    }, schedules=schedules)
    # Refresh can replace the coordinator's home while the initial stored model remains.
    ha_hass.data[DOMAIN] = {"entry": {
        "intuis_home": SimpleNamespace(rooms={}, schedules=[]),
        "coordinator": SimpleNamespace(data={"intuis_home": home, "rooms": {}},
                                       last_update_success=True, update_interval=None),
    }}
    result = await async_get_config_entry_diagnostics(
        ha_hass, SimpleNamespace(entry_id="entry", version=1)
    )
    export = result["planning_export"]
    encoded = json.dumps(export, allow_nan=False)
    assert "CLOUD-" not in encoded and "SECRET" not in encoded
    assert export["timezone"] == "Europe/Paris"
    assert export["week_start"] == "Monday"
    assert export["timetable_unit"] == "minutes_from_week_start"
    assert export["captured_at"].endswith("+00:00")
    assert [s["name"] for s in export["schedules"]] == [s["name"] for s in raw]
    assert [s["selected"] for s in export["schedules"]] == [True, False, False, True, False]
    assert export["rooms"] == [
        {"id": "room_1", "name": "Salon"}, {"id": "room_2", "name": "Entrée"},
        {"id": "room_3", "name": None},
    ]
    normal, rouge, empty, tariff, event = export["schedules"]
    assert normal["timetable"] == raw[0]["timetable"]
    assert len(normal["zones"]) == 3  # Includes a zone unused by the timetable.
    assert normal["zones"][0]["rooms_temp"] == [{"room_id": "room_1", "temp": 17.5}]
    assert normal["zones"][1]["rooms"][1] == {
        "id": "room_2", "therm_setpoint_temperature": None, "therm_setpoint_fp": "comfort",
    }
    assert rouge["zones"][0]["rooms"][0]["id"] == "room_2"
    assert rouge["zones"][0]["rooms_temp"][1]["temp"] is None
    assert normal["away_temp"] == 12.5 and normal["hg_temp"] == 7
    assert empty["zones"] == [] and empty["timetable"] == []
    assert tariff["tariff"] == "tempo" and tariff["version"] == 2
    assert tariff["zones"][0]["price"] == 0.1234
    assert event["zones"][0]["modules"] == [{"id": "module_1", "dhw_state": "on"}]
    assert event["zones"][1]["modules"] == [{"id": "module_1", "dhw_state": "off"}]
    # The exported schedule schema is readable by the existing model parser.
    reconstructed = IntuisSchedule.from_dict(normal)
    assert reconstructed.zones[1].rooms[1].therm_setpoint_fp == "comfort"
    assert reconstructed.timetables[-1].m_offset == 10050
    normal["zones"][0]["rooms_temp"][0]["temp"] = 99
    normal["timetable"][0]["m_offset"] = 100
    assert schedules[0].zones[0].rooms_temp[0].temp == 17.5
    assert schedules[0].timetables[0].m_offset == 0


async def test_planning_export_room_aliases_match_diagnostic_states(ha_hass):
    room = SimpleNamespace(name="Bureau", temperature=20)
    ha_hass.data[DOMAIN] = {"entry": {
        "intuis_home": SimpleNamespace(rooms={"cloud-room": room}, schedules=[]),
        "coordinator": SimpleNamespace(data={"rooms": {"cloud-room": room}},
                                       last_update_success=False, update_interval=None),
    }}
    result = await async_get_config_entry_diagnostics(
        ha_hass, SimpleNamespace(entry_id="entry", version=1)
    )
    assert result["planning_export"]["rooms"] == [{"id": "room_1", "name": "Bureau"}]
    assert result["rooms"]["room_1"]["temperature"] == 20
    assert result["coordinator"]["last_update_success"] is False
