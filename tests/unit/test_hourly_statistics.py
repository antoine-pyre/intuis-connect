"""Native worker checks for TheFab21-derived external hourly capabilities."""
from datetime import datetime, timezone
import asyncio
import inspect
from homeassistant.components.recorder.tasks import SynchronizeTask
import pytest
from homeassistant.components.recorder import statistics
from homeassistant.components.energy.data import DEVICE_CONSUMPTION_SCHEMA
from custom_components.intuis_connect.external_statistics import metadata, statistic_id
from .test_history_import import live_recorder as _live_recorder


@pytest.fixture
async def live_recorder(ha_hass,tmp_path):
    async for instance in _live_recorder.__wrapped__(ha_hass,tmp_path):
        yield instance


async def test_external_series_import_query_and_energy_selection(ha_hass,live_recorder):
    meta=metadata('home','room','Room hourly energy')
    statistics.async_add_external_statistics(ha_hass,meta,[{'start':datetime(2026,10,25,tzinfo=timezone.utc),'state':0.5,'sum':0.5}])
    await ha_hass.async_block_till_done()
    if "event" in inspect.signature(SynchronizeTask).parameters:
        barrier = asyncio.Event()
        live_recorder.queue_task(SynchronizeTask(barrier))
        await asyncio.wait_for(barrier.wait(), 15)
    else:
        barrier = asyncio.get_running_loop().create_future()
        live_recorder.queue_task(SynchronizeTask(barrier))
        await asyncio.wait_for(barrier, 15)
    result=await live_recorder.async_add_executor_job(statistics.list_statistic_ids,ha_hass,None,'sum')
    def db_rows():
        from sqlalchemy import select
        from homeassistant.components.recorder.db_schema import StatisticsMeta
        with live_recorder.get_session() as session:
            return [(m.statistic_id, m.has_sum) for m in session.scalars(select(StatisticsMeta))]
    assert len(result)==1, await live_recorder.async_add_executor_job(db_rows)
    assert result[0]['statistic_id']==meta['statistic_id']
    assert result[0]['statistics_unit_of_measurement']=='kWh'
    assert result[0]['source']=='intuis_connect'
    assert DEVICE_CONSUMPTION_SCHEMA({'stat_consumption':meta['statistic_id']})['stat_consumption']==meta['statistic_id']
    assert statistic_id('home',None)!=statistic_id('home','room')


async def test_actual_http_hourly_chunk_boundaries_are_not_added(cloud_responses):
    import aiohttp
    from .test_api_energy import client
    from custom_components.intuis_connect.utils.const import BASE_URLS, ROOMMEASURE_PATH
    start=int(datetime(2026,1,1,tzinfo=timezone.utc).timestamp())
    boundary=start+42*86400
    cloud_responses.post(BASE_URLS[0]+ROOMMEASURE_PATH,payload={'body':[{'beg_time':boundary,'step_time':3600,'value':[[500]]}]})
    cloud_responses.post(BASE_URLS[0]+ROOMMEASURE_PATH,payload={'body':[{'beg_time':boundary,'step_time':3600,'value':[[500]]}]})
    async with aiohttp.ClientSession() as session:
        result=await client(session).async_get_room_energy_hourly('room',start,boundary+3600)
    assert result==[(boundary,500)]
    assert sum(len(requests) for requests in cloud_responses.requests.values())==2


def test_staging_deduplicates_but_rejects_conflicts_and_holes():
    from custom_components.intuis_connect.hourly_series import stage_hourly
    from custom_components.intuis_connect.intuis_api.api import APIError
    result=stage_hourly([(0,500),(0,500),(3600,0)],0,7200)
    assert [value for _,value in result]==[0.5,0]
    for samples in ([(0,500),(0,600),(3600,0)],[(0,500)]):
        with pytest.raises(APIError):
            stage_hourly(samples,0,7200)


@pytest.mark.parametrize('time,expected', [('2026-10-26T10:14:59+00:00','2026-10-26T09:00:00+00:00'),('2026-10-26T10:15:00+00:00','2026-10-26T10:00:00+00:00')])
def test_closed_hours_wait_for_fifteen_minutes(time,expected):
    from custom_components.intuis_connect.hourly_series import closed_hour_end
    assert closed_hour_end(datetime.fromisoformat(time))==int(datetime.fromisoformat(expected).timestamp())


@pytest.mark.parametrize('day,next_day,hours',[(datetime(2026,3,29),datetime(2026,3,30),23),(datetime(2026,10,25),datetime(2026,10,26),25)])
def test_hourly_coverage_follows_utc_through_dst(day,next_day,hours):
    from zoneinfo import ZoneInfo
    from custom_components.intuis_connect.hourly_series import stage_hourly
    zone=ZoneInfo('Europe/Paris')
    start=int(day.replace(tzinfo=zone).timestamp())
    end=int(next_day.replace(tzinfo=zone).timestamp())
    assert len(stage_hourly([(ts,0) for ts in range(start,end,3600)],start,end))==hours


@pytest.mark.parametrize('value',[None,-1,float('nan'),float('inf'),True,'500'])
def test_invalid_hourly_values_cannot_be_imported(value):
    from custom_components.intuis_connect.hourly_series import stage_hourly
    from custom_components.intuis_connect.intuis_api.api import APIError
    with pytest.raises(APIError):
        stage_hourly([(0,value)],0,3600)


@pytest.mark.parametrize('payload',[{},[],{'error':{'code':1}},{'body':[{'beg_time':0,'value':[[1]]}]}])
async def test_malformed_http_hourly_response_is_typed_error(cloud_responses,payload):
    import aiohttp
    from .test_api_energy import client
    from custom_components.intuis_connect.utils.const import BASE_URLS, ROOMMEASURE_PATH
    from custom_components.intuis_connect.intuis_api.api import APIError
    cloud_responses.post(BASE_URLS[0]+ROOMMEASURE_PATH,payload=payload)
    async with aiohttp.ClientSession() as session:
        with pytest.raises(APIError):
            await client(session).async_get_room_energy_hourly('room',0,3600)


@pytest.mark.parametrize('samples',[[(0,0),(3600,0)],[(-3600,0),(0,0)],[(1800,0)]])
def test_late_cloud_samples_outside_the_closed_window_are_rejected(samples):
    from custom_components.intuis_connect.hourly_series import stage_hourly
    from custom_components.intuis_connect.intuis_api.api import APIError
    with pytest.raises(APIError):
        stage_hourly(samples,0,3600)
