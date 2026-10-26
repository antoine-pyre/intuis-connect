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
