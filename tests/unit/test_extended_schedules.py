"""Adapted planning capabilities from TheFab21 #22/#24, via real HA services."""
from copy import deepcopy
import pytest
from homeassistant.exceptions import ServiceValidationError
from .test_multi_home_services import homes as _homes_fixture, call, args


@pytest.fixture
async def homes(ha_hass, ha_entry_factory):
    return await _homes_fixture.__wrapped__(ha_hass, ha_entry_factory)


async def test_inactive_schedule_target_preserves_active_and_other_home(homes):
    target = deepcopy(homes.second.home.schedules[0])
    target.id, target.name, target.selected = 'inactive', 'Holiday', False
    homes.second.home.schedules.append(target)
    original = deepcopy(homes.second.home.schedules[0].timetables)
    await call(homes, 'set_schedule_slot', home_id='second', schedule_id='inactive',
               schedule_name='Holiday', **args('set_schedule_slot'))
    payload = homes.second.api.async_sync_schedule.call_args.kwargs
    assert payload['schedule_id'] == 'inactive'
    assert homes.second.home.schedules[0].selected and not target.selected
    assert [(t.m_offset,t.zone_id) for t in homes.second.home.schedules[0].timetables] == [(t.m_offset,t.zone_id) for t in original]
    homes.first.api.async_sync_schedule.assert_not_awaited()


@pytest.mark.parametrize('target', [dict(schedule_id='wrong'), dict(schedule_id='schedule-second',schedule_name='wrong')])
async def test_invalid_target_rejected_before_transport(homes,target):
    with pytest.raises(ServiceValidationError):
        await call(homes,'set_schedule_slot',home_id='second',**target,**args('set_schedule_slot'))
    homes.second.api.async_sync_schedule.assert_not_awaited()


@pytest.mark.parametrize('payload', [
    {}, {'timetable': []}, {'timetable': [{'m_offset': True,'zone_id': 1}]},
    {'timetable': [{'m_offset': 0,'zone_id': 1}]*2}, {'away_temp': 25.5},
    {'hg_temp': 15.5}, {'away_temp': float('nan')}, {'timetable':'not json'},
    {'timetable': [{'m_offset': i,'zone_id': 1} for i in range(513)]},
])
def test_complete_schedule_schema_rejects_invalid_payloads(payload):
    import voluptuous as vol
    from custom_components.intuis_connect.services import SYNC_SCHEDULE_SCHEMA
    with pytest.raises(vol.Invalid):
        SYNC_SCHEDULE_SCHEMA(payload)


def test_complete_schedule_schema_parses_original_json_without_mutation():
    from custom_components.intuis_connect.services import SYNC_SCHEDULE_SCHEMA
    result = SYNC_SCHEDULE_SCHEMA({'timetable':'[{"zone_id":2,"m_offset":0}]','away_temp':19.5})
    assert result == {'timetable':[{'zone_id':2,'m_offset':0}],'away_temp':19.5}


async def test_full_save_and_temperature_only_confirmed(homes):
    target = homes.second.home.schedules[0]
    await call(homes,'sync_schedule', home_id='second', timetable=[{'m_offset':500,'zone_id':2}],away_temp=19.5,hg_temp=8.5)
    assert [(t.m_offset,t.zone_id) for t in target.timetables] == [(500,2)]
    assert (target.away_temp,target.hg_temp)==(19.5,8.5)
    await call(homes,'sync_schedule',home_id='second',away_temp=16.5)
    assert [(t.m_offset,t.zone_id) for t in target.timetables]==[(500,2)]
    assert target.away_temp==16.5


async def test_unknown_zone_and_cloud_error_preserve_state(homes):
    from custom_components.intuis_connect.intuis_api.api import APIError
    target = homes.second.home.schedules[0]
    with pytest.raises(ServiceValidationError):
        await call(homes,'sync_schedule',home_id='second',timetable=[{'m_offset':0,'zone_id':999}])
    homes.second.api.async_sync_schedule.assert_not_awaited()
    homes.second.api.async_sync_schedule.side_effect=APIError('offline')
    with pytest.raises(APIError):
        await call(homes,'sync_schedule',home_id='second',away_temp=19.5)
    assert target.away_temp==16


async def test_renamed_schedule_names_keep_identity_and_user_name(homes):
    from types import SimpleNamespace
    from homeassistant.helpers import device_registry as dr
    from custom_components.intuis_connect.number import IntuisZoneTemperatureNumber
    from custom_components.intuis_connect.calendar import IntuisScheduleCalendar
    if hasattr(dr, 'async_setup'):
        dr.async_setup(homes.hass)
    await dr.async_load(homes.hass)
    registry = dr.async_get(homes.hass)
    schedule = homes.second.home.schedules[0]
    coordinator = SimpleNamespace(data={'intuis_home': homes.second.home})
    zone = schedule.zones[0]
    number = IntuisZoneTemperatureNumber(coordinator,homes.second.api,'second',schedule,zone,zone.rooms_temp[0],'Room')
    number.hass = homes.hass
    number.async_write_ha_state = lambda: None
    calendar = IntuisScheduleCalendar(coordinator,homes.second.api,'second',homes.second.home,schedule)
    ids = number.unique_id, calendar.unique_id
    device = registry.async_get_or_create(config_entry_id=homes.second.entry.entry_id, identifiers=number.device_info["identifiers"], name=number.device_info["name"])
    registry.async_update_device(device.id, name_by_user='My custom device')
    schedule.name='Renamed'
    number._handle_coordinator_update()
    assert number.device_info['name']=='Schedule Renamed'
    assert calendar.name=='Schedule Renamed'
    assert registry.async_get(device.id).name=='Schedule Renamed'
    assert registry.async_get(device.id).name_by_user=='My custom device'
    assert (number.unique_id,calendar.unique_id)==ids
