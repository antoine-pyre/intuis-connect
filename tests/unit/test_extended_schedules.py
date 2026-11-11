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
    # Later polls without a rename never read the device registry.
    lookups=[]
    lookup='async_get_devices' if hasattr(registry,'async_get_devices') else 'async_get_device'
    original=getattr(registry,lookup)
    setattr(registry,lookup,lambda **kwargs: lookups.append(kwargs) or original(**kwargs))
    number._handle_coordinator_update()
    number._handle_coordinator_update()
    assert lookups==[]
    schedule.name='Weekend'
    number._handle_coordinator_update()
    assert len(lookups)==1 and registry.async_get(device.id).name=='Schedule Weekend'


async def test_actual_summary_has_all_days_inherited_zone_and_room_names(homes):
    from types import SimpleNamespace
    from custom_components.intuis_connect.entity.intuis_home_entity import IntuisScheduleSummarySensor
    target = homes.second.home.schedules[0]
    target.timetables = [target.timetables[1]]  # first transition Monday 08:00, cyclic all week
    entity = IntuisScheduleSummarySensor(SimpleNamespace(data={'intuis_home':homes.second.home}), 'second',target)
    attrs = entity.extra_state_attributes
    assert attrs['home_id']=='second'
    assert attrs['home_name']==homes.second.home.name
    assert attrs['room_names']=={'room-second':'Room'}
    assert len(attrs['weekly_timetable'])==7
    assert attrs['weekly_timetable']['Monday'][0]=={'time':'00:00','zone':'Eco'}
    assert attrs['weekly_timetable']['Tuesday']==[{'time':'00:00','zone':'Eco'}]
    assert attrs['timetable']==[{'m_offset':480,'zone_id':2}]


async def test_complete_save_serializes_with_number_and_refresh(homes):
    import asyncio
    from types import SimpleNamespace
    from custom_components.intuis_connect.number import IntuisZoneTemperatureNumber
    h = homes.second
    schedule = h.home.schedules[0]
    zone = schedule.zones[0]
    coordinator = SimpleNamespace(data={'intuis_home':h.home},async_request_refresh=h.coordinator.async_request_refresh)
    number = IntuisZoneTemperatureNumber(coordinator,h.api,'second',schedule,zone,zone.rooms_temp[0],'Room')
    number.hass=homes.hass
    number.async_write_ha_state=lambda: None
    entered, release = asyncio.Event(), asyncio.Event()
    payloads=[]
    async def sync(**payload):
        payloads.append(deepcopy(payload))
        if len(payloads)==1:
            entered.set()
            await release.wait()
    h.api.async_sync_schedule.side_effect=sync
    first=asyncio.create_task(call(homes,'sync_schedule',home_id='second',away_temp=18.5,timetable=[{'m_offset':500,'zone_id':2}]))
    await entered.wait()
    second=asyncio.create_task(number.async_set_native_value(19.5))
    await asyncio.sleep(0)
    assert len(payloads)==1
    h.home.schedules=deepcopy(h.home.schedules)
    release.set()
    await first
    await second
    assert payloads[1]['away_temp']==18.5
    assert payloads[1]['timetable']==[{'m_offset':500,'zone_id':2}]
    assert payloads[1]['zones'][0]['rooms_temp'][0]['temp']==19.5


async def test_complete_save_late_ack_does_not_refresh_unloaded_entry(homes):
    import asyncio
    from custom_components.intuis_connect.utils.const import DOMAIN
    entered,release=asyncio.Event(),asyncio.Event()
    async def sync(**payload):
        entered.set()
        await release.wait()
    homes.second.api.async_sync_schedule.side_effect=sync
    task=asyncio.create_task(call(homes,'sync_schedule',home_id='second',hg_temp=8.5))
    await entered.wait()
    homes.hass.data[DOMAIN].pop(homes.second.entry.entry_id)
    release.set()
    await task
    homes.second.coordinator.async_request_refresh.assert_not_awaited()
