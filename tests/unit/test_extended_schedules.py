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
