"""Multi-home service contracts exercised through Home Assistant's registry."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import builtins
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol
import yaml
from homeassistant.config_entries import ConfigEntryState, current_entry
from homeassistant.exceptions import ServiceValidationError

from custom_components.intuis_connect import async_setup_entry, async_unload_entry
from custom_components.intuis_connect.entity.intuis_schedule import IntuisSchedule
from custom_components.intuis_connect.services import SERVICES, async_register_services
from custom_components.intuis_connect.utils.const import DOMAIN


COMPONENT = Path(__file__).parents[2] / "custom_components" / DOMAIN


def schedule(home_id, name="Week"):
    return IntuisSchedule.from_dict(
        {
            "id": f"schedule-{home_id}",
            "name": name,
            "type": "therm",
            "selected": True,
            "away_temp": 16,
            "hg_temp": 7,
            "timetable": [
                {"m_offset": 0, "zone_id": 1},
                {"m_offset": 480, "zone_id": 2},
            ],
            "zones": [
                {
                    "id": i,
                    "name": name,
                    "type": 0,
                    "rooms_temp": [{"room_id": f"room-{home_id}", "temp": 20.0}],
                }
                for i, name in [(1, "Night"), (2, "Eco")]
            ],
        }
    )


def model(home_id, *, name="Week"):
    return SimpleNamespace(
        id=home_id,
        name=home_id,
        schedules=[schedule(home_id, name)],
        rooms={f"room-{home_id}": SimpleNamespace(name="Room")},
    )


@pytest.fixture
async def homes(ha_hass, ha_entry_factory):
    ha_hass.data[DOMAIN] = {}

    def add(home_id):
        entry = ha_entry_factory(home_id=home_id)
        home = model(home_id)
        api = SimpleNamespace(
            async_switch_schedule=AsyncMock(),
            async_sync_schedule=AsyncMock(),
            async_get_homes_data=AsyncMock(return_value=deepcopy(home)),
            _schedule_mutation_locks={},
        )
        coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
        data = {"intuis_home": home, "api": api, "coordinator": coordinator}
        ha_hass.data[DOMAIN][entry.entry_id] = data
        return SimpleNamespace(
            entry=entry, home=home, api=api, coordinator=coordinator, data=data
        )

    first, second = add("first"), add("second")
    await async_register_services(ha_hass, first.entry)
    await async_register_services(ha_hass, second.entry)
    return SimpleNamespace(hass=ha_hass, first=first, second=second, add=add)


def args(service):
    return {
        "switch_schedule": {"schedule_name": "Week"},
        "set_schedule_slot": {
            "day": "0",
            "start_time": "07:00",
            "end_time": "09:00",
            "zone_name": "Eco",
        },
        "set_zone_temperature": {
            "schedule_name": "Week",
            "zone_name": "Eco",
            "room_name": "Room",
            "temperature": 19.5,
        },
        "sync_schedule": {"away_temp": 17.5},
        "refresh_schedules": {},
        "import_energy_history": {"days": 2},
        "recalculate_cost_history": {"days": 2},
    }[service]


async def call(homes, service, **kwargs):
    await homes.hass.services.async_call(DOMAIN, service, kwargs, blocking=True)


@pytest.mark.parametrize("service", SERVICES)
async def test_all_services_accept_home_id_and_only_target_second(
    homes, monkeypatch, service
):
    async def run_exclusive(job):
        return await job

    managers = {
        home.entry.entry_id: SimpleNamespace(
            start=Mock(return_value=True), async_run_exclusive=run_exclusive
        )
        for home in (homes.first, homes.second)
    }
    getter = AsyncMock(side_effect=lambda hass, eid: managers[eid])
    monkeypatch.setattr(
        "custom_components.intuis_connect.services.async_get_import_manager", getter
    )
    recalculate = AsyncMock(return_value={"status": "completed", "errors": []})
    monkeypatch.setattr(
        "custom_components.intuis_connect.services.async_recalculate_costs", recalculate
    )
    for home in (homes.first, homes.second):
        home.data["options"] = {"cost_statistics": True, "cost_price_mode": "fixed"}
    await call(homes, service, home_id="second", **args(service))
    homes.first.api.async_switch_schedule.assert_not_awaited()
    homes.first.api.async_sync_schedule.assert_not_awaited()
    homes.first.api.async_get_homes_data.assert_not_awaited()
    if service == "import_energy_history":
        getter.assert_awaited_once_with(homes.hass, homes.second.entry.entry_id)
        managers[homes.first.entry.entry_id].start.assert_not_called()
        managers[homes.second.entry.entry_id].start.assert_called_once_with(
            homes.second.api,
            homes.second.home,
            days=2,
            room_filter=None,
            home_id="second",
        )
    elif service == "recalculate_cost_history":
        getter.assert_awaited_once_with(homes.hass, homes.second.entry.entry_id)
        recalculate.assert_awaited_once()
        assert recalculate.call_args.args[1] == homes.second.entry.entry_id
    elif service == "switch_schedule":
        homes.second.api.async_switch_schedule.assert_awaited_once_with(
            "second", "schedule-second"
        )
    elif service == "refresh_schedules":
        homes.second.api.async_get_homes_data.assert_awaited_once()
    else:
        assert (
            homes.second.api.async_sync_schedule.call_args.kwargs["schedule_id"]
            == "schedule-second"
        )
        assert homes.first.home.schedules[0].zones[1].rooms_temp[0].temp == 20


@pytest.mark.parametrize("service", SERVICES)
async def test_unknown_home_rejected_before_any_command_or_import(
    homes, monkeypatch, service
):
    getter = AsyncMock()
    monkeypatch.setattr(
        "custom_components.intuis_connect.services.async_get_import_manager", getter
    )
    with pytest.raises(ServiceValidationError, match="not loaded"):
        await call(homes, service, home_id="missing", **args(service))
    for home in (homes.first, homes.second):
        home.api.async_switch_schedule.assert_not_awaited()
        home.api.async_sync_schedule.assert_not_awaited()
        home.api.async_get_homes_data.assert_not_awaited()
    getter.assert_not_awaited()


@pytest.mark.parametrize("service", SERVICES)
@pytest.mark.parametrize("home_id", ["", "   "])
async def test_explicit_empty_home_never_falls_back_to_first(homes, service, home_id):
    with pytest.raises(vol.Invalid):
        await call(homes, service, home_id=home_id, **args(service))
    homes.first.api.async_switch_schedule.assert_not_awaited()
    homes.first.api.async_sync_schedule.assert_not_awaited()
    homes.first.api.async_get_homes_data.assert_not_awaited()


@pytest.mark.parametrize(
    "service", ["switch_schedule", "set_schedule_slot", "set_zone_temperature"]
)
async def test_implicit_mutations_preserve_first_home_default_and_warn(
    homes, caplog, service
):
    await call(homes, service, **args(service))
    assert "using first home" in caplog.text
    homes.second.api.async_switch_schedule.assert_not_awaited()
    homes.second.api.async_sync_schedule.assert_not_awaited()
    if service == "switch_schedule":
        homes.first.api.async_switch_schedule.assert_awaited_once()
    else:
        homes.first.api.async_sync_schedule.assert_awaited_once()


async def test_refresh_without_target_refreshes_all_homes(homes):
    await call(homes, "refresh_schedules")
    homes.first.api.async_get_homes_data.assert_awaited_once()
    homes.second.api.async_get_homes_data.assert_awaited_once()


async def test_import_without_target_starts_all_or_matching_room_homes(
    homes, monkeypatch
):
    managers = {
        h.entry.entry_id: SimpleNamespace(start=Mock(return_value=True))
        for h in (homes.first, homes.second)
    }
    getter = AsyncMock(side_effect=lambda hass, eid: managers[eid])
    monkeypatch.setattr(
        "custom_components.intuis_connect.services.async_get_import_manager", getter
    )
    await call(homes, "import_energy_history", days=2, room_name="")
    assert getter.await_count == 2
    getter.reset_mock()
    homes.first.home.rooms["room-first"].name = "Other"
    await call(homes, "import_energy_history", days=2, room_name="Room")
    getter.assert_awaited_once_with(homes.hass, homes.second.entry.entry_id)


@pytest.mark.parametrize("home_id", [None, "second"])
async def test_import_bad_room_is_validated_before_starting_any_task(
    homes, monkeypatch, home_id
):
    getter = AsyncMock()
    monkeypatch.setattr(
        "custom_components.intuis_connect.services.async_get_import_manager", getter
    )
    with pytest.raises(ServiceValidationError, match="Room missing"):
        await call(
            homes,
            "import_energy_history",
            days=2,
            room_name="missing",
            **({"home_id": home_id} if home_id else {}),
        )
    getter.assert_not_awaited()


@pytest.mark.parametrize(
    "service,field",
    [
        ("switch_schedule", "schedule_name"),
        ("set_schedule_slot", "zone_name"),
        ("set_zone_temperature", "schedule_name"),
        ("set_zone_temperature", "zone_name"),
        ("set_zone_temperature", "room_name"),
    ],
)
async def test_unknown_names_rejected_on_current_target(homes, service, field):
    values = args(service)
    values[field] = "missing"
    with pytest.raises(ServiceValidationError):
        await call(homes, service, home_id="second", **values)
    homes.second.api.async_switch_schedule.assert_not_awaited()
    homes.second.api.async_sync_schedule.assert_not_awaited()


async def test_new_names_after_refresh_need_no_reregistration(homes):
    fresh = model("second", name="New Week")
    fresh.schedules[0].zones[1].name = "New Eco"
    fresh.rooms["room-second"].name = "Renamed Room"
    homes.second.api.async_get_homes_data.return_value = fresh
    await call(homes, "refresh_schedules", home_id="second")
    await call(homes, "switch_schedule", home_id="second", schedule_name="New Week")
    values = args("set_zone_temperature")
    values.update(
        schedule_name="New Week",
        zone_name="New Eco",
        room_name="Renamed Room",
        home_id="second",
    )
    await call(homes, "set_zone_temperature", **values)
    assert (
        homes.second.api.async_sync_schedule.call_args.kwargs["zones"][1]["rooms_temp"][
            0
        ]["temp"]
        == 19.5
    )


async def test_add_and_reload_entries_keep_services_usable(homes):
    third = homes.add("third")
    third.home.schedules[0].name = "Third Week"
    await async_register_services(homes.hass, third.entry)
    await call(homes, "switch_schedule", home_id="third", schedule_name="Third Week")
    third.api.async_switch_schedule.assert_awaited_once()
    replacement = model("third", name="Reloaded Week")
    replacement_api = SimpleNamespace(async_switch_schedule=AsyncMock())
    homes.hass.data[DOMAIN][third.entry.entry_id] = {
        "intuis_home": replacement,
        "api": replacement_api,
    }
    await async_register_services(homes.hass, third.entry)
    await call(homes, "switch_schedule", home_id="third", schedule_name="Reloaded Week")
    replacement_api.async_switch_schedule.assert_awaited_once_with(
        "third", "schedule-third"
    )
    assert third.api.async_switch_schedule.await_count == 1


async def test_first_unload_keeps_services_and_last_unload_removes_them(
    homes, monkeypatch
):
    monkeypatch.setattr(
        homes.hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    )
    assert await async_unload_entry(homes.hass, homes.first.entry)
    assert all(homes.hass.services.has_service(DOMAIN, s) for s in SERVICES)
    await call(homes, "switch_schedule", home_id="second", schedule_name="Week")
    homes.second.api.async_switch_schedule.assert_awaited_once()
    assert await async_unload_entry(homes.hass, homes.second.entry)
    assert all(not homes.hass.services.has_service(DOMAIN, s) for s in SERVICES)


async def test_failed_unload_keeps_registered_services(homes, monkeypatch):
    monkeypatch.setattr(
        homes.hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=False),
    )
    assert not await async_unload_entry(homes.hass, homes.first.entry)
    assert all(homes.hass.services.has_service(DOMAIN, s) for s in SERVICES)


async def test_refresh_snapshots_entries_and_ignores_removed_home_response(homes):
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed():
        entered.set()
        await release.wait()
        return model("first", name="Late")

    homes.first.api.async_get_homes_data.side_effect = delayed
    task = asyncio.create_task(call(homes, "refresh_schedules"))
    await entered.wait()
    homes.hass.data[DOMAIN].pop(homes.first.entry.entry_id)
    homes.hass.data[DOMAIN].pop(homes.second.entry.entry_id)
    homes.add("third")
    release.set()
    await task
    assert homes.first.home.schedules[0].name == "Week"
    homes.first.coordinator.async_request_refresh.assert_not_awaited()
    homes.second.api.async_get_homes_data.assert_not_awaited()


@pytest.mark.parametrize("service", ["set_schedule_slot", "set_zone_temperature"])
async def test_late_mutation_ack_does_not_refresh_unloaded_coordinator(homes, service):
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed(**kwargs):
        entered.set()
        await release.wait()

    homes.second.api.async_sync_schedule.side_effect = delayed
    task = asyncio.create_task(call(homes, service, home_id="second", **args(service)))
    await entered.wait()
    homes.hass.data[DOMAIN].pop(homes.second.entry.entry_id)
    release.set()
    await task
    homes.second.coordinator.async_request_refresh.assert_not_awaited()


async def test_static_descriptions_match_schemas_and_translations(homes):
    import json

    descriptions = yaml.safe_load((COMPONENT / "services.yaml").read_text())
    for language in ("en", "fr"):
        translated = json.loads(
            (COMPONENT / "translations" / f"{language}.json").read_text()
        )["services"]
        for service in SERVICES:
            schema = homes.hass.services.async_services()[DOMAIN][service].schema
            schema_fields = {str(key) for key in schema.schema}
            assert set(descriptions[service]["fields"]) == schema_fields
            assert set(translated[service]["fields"]) == schema_fields
            assert "home_id" in schema_fields
            for name in ("schedule_name", "zone_name", "room_name"):
                if name in descriptions[service]["fields"]:
                    assert "text" in descriptions[service]["fields"][name]["selector"]


async def setup_real_entry(homes, monkeypatch, entry=None):
    """Run the actual async_setup_entry for the first home with simulated cloud."""
    entry = entry or homes.first.entry
    home = homes.first.home
    api = homes.first.api
    api.home_timezone = "UTC"
    api.circuit_breaker = SimpleNamespace(is_open=False)
    api.async_refresh_access_token = AsyncMock()
    api.async_get_home_status = AsyncMock(return_value={"rooms": [], "modules": []})
    api.async_get_config = AsyncMock(return_value={"modules": [{"id": "gateway"}]})
    api.set_rate_limit_callback = lambda cb: None
    api.async_get_homes_data.return_value = home
    monkeypatch.setattr(
        "custom_components.intuis_connect.IntuisAPI", lambda *a, **kw: api
    )
    # Transport is already simulated; do not initialize DNS/zeroconf discovery.
    monkeypatch.setattr(
        "custom_components.intuis_connect.async_get_clientsession", lambda hass: None
    )
    monkeypatch.setattr(
        homes.hass.config_entries, "async_forward_entry_setups", AsyncMock()
    )
    # Native HA bootstrap initializes the frame helper on recent releases.
    from homeassistant.helpers import frame

    if hasattr(frame, "async_setup"):
        monkeypatch.setattr(frame._hass, "hass", homes.hass)
    entry._async_set_state(homes.hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
    token = current_entry.set(entry)
    try:
        assert await async_setup_entry(homes.hass, entry)
    finally:
        current_entry.reset(token)
    return entry


async def test_setup_and_refresh_do_not_write_installed_component(homes, monkeypatch):
    """Emulate a read-only component while allowing HA's native temporary Store."""
    component_root = COMPONENT.resolve()
    builtins_open, io_open = builtins.open, io.open
    attempts = []

    def readonly_open(original):
        def open_file(file, mode="r", *a, **kw):
            if isinstance(file, (str, bytes, Path)) and any(
                flag in mode for flag in "wax+"
            ):
                path = Path(file).resolve()
                if path.is_relative_to(component_root):
                    attempts.append(path)
                    raise PermissionError("Installed component is read only")
            return original(file, mode, *a, **kw)

        return open_file

    monkeypatch.setattr(builtins, "open", readonly_open(builtins_open))
    monkeypatch.setattr(io, "open", readonly_open(io_open))
    entry = await setup_real_entry(homes, monkeypatch)
    await call(homes, "refresh_schedules", home_id="first")
    assert not attempts
    coordinator = homes.hass.data[DOMAIN][entry.entry_id]["coordinator"]
    await coordinator.async_shutdown()


@pytest.mark.parametrize("days", [0, 1.5, True, 731, float("nan")])
async def test_import_rejects_invalid_day_count_before_creating_task(
    homes, monkeypatch, days
):
    getter = AsyncMock()
    monkeypatch.setattr(
        "custom_components.intuis_connect.services.async_get_import_manager", getter
    )
    with pytest.raises(vol.Invalid):
        await call(homes, "import_energy_history", home_id="second", days=days)
    getter.assert_not_awaited()
