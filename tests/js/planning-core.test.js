'use strict';
// Run with: node --test tests/js/*.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const core = require('../../custom_components/intuis_connect/resources/planning/planning-core.js');

const timetable = [
  { m_offset: 0, zone_id: 1 },
  { m_offset: 420, zone_id: 2 },
  { m_offset: 1320, zone_id: 1 },
];

function summary(overrides = {}) {
  return {
    state: 'Semaine',
    attributes: {
      home_id: 'home-1',
      home_name: 'Maison',
      schedule_id: 'sched-1',
      is_active: true,
      away_temperature: 16,
      frost_guard_temperature: 7,
      room_names: { r1: 'Salon', r2: 'Chambre' },
      timetable,
      zones: [
        { id: 1, name: 'Nuit', type: 1, room_temperatures: { r1: 17, r2: 16 } },
        { id: 2, name: 'Confort', type: 0, room_temperatures: { r1: 20, r2: 19.5 } },
      ],
      ...overrides,
    },
  };
}

function homes(states) {
  return core.parseHomes(states);
}

test('same-day midnight ends at the next midnight, another day at its start', () => {
  assert.deepEqual(core.slotOffsets('6', '22:00', '6', '00:00'), [9960, 10080]);
  assert.deepEqual(core.slotOffsets('0', '22:00', '1', '00:00'), [1320, 1440]);
  assert.deepEqual(core.slotOffsets('4', '22:00', '0', '06:00'), [7080, 360]);
  assert.deepEqual(core.slotOffsets('0', '07:00', '0', '11:00:00'), [420, 660]);
  assert.deepEqual(core.slotOffsets('0', '00:00', '0', '00:00'), [0, 1440]);
});

test('invalid or ambiguous slots are rejected instead of rounded', () => {
  for (const args of [
    ['0', '10:00', '0', '09:00'],
    ['0', '10:00', '0', '10:00'],
    ['0', '10:00:30', '0', '11:00'],
    ['7', '10:00', '0', '11:00'],
    ['', '10:00', '0', '11:00'],
    ['0', '24:00', '0', '11:00'],
  ]) {
    assert.throws(() => core.slotOffsets(...args), Error, String(args));
  }
  // A full week (Monday 00:00 → Monday 00:00 of another week) is ambiguous.
  assert.throws(() => core.replaceInterval(timetable, 0, 10080, 2));
});

test('replacing an interval removes inner transitions and keeps the complement', () => {
  const edited = core.replaceInterval(
    [...timetable, { m_offset: 480, zone_id: 3 }], 420, 660, 4);
  assert.deepEqual(edited, [
    { m_offset: 0, zone_id: 1 },
    { m_offset: 420, zone_id: 4 },
    { m_offset: 660, zone_id: 3 },
    { m_offset: 1320, zone_id: 1 },
  ]);
  for (let minute = 0; minute < core.MINUTES_PER_WEEK; minute += 15) {
    if (minute < 420 || minute >= 660) {
      assert.equal(core.zoneAt(edited, minute),
        core.zoneAt([...timetable, { m_offset: 480, zone_id: 3 }], minute), String(minute));
    }
  }
});

test('an interval across the week boundary wraps without an offset 10080', () => {
  const edited = core.replaceInterval(timetable, 9960, 360, 3);
  // Like timetable.py, no offset 0 is added: Monday midnight inherits Sunday's zone.
  assert.deepEqual(edited, [
    { m_offset: 360, zone_id: 1 },
    { m_offset: 420, zone_id: 2 },
    { m_offset: 1320, zone_id: 1 },
    { m_offset: 9960, zone_id: 3 },
  ]);
  assert.equal(core.zoneAt(edited, 0), 3);
});

test('days inherit the zone active at midnight, including Sunday into Monday', () => {
  const week = [{ m_offset: 420, zone_id: 2 }, { m_offset: 9960, zone_id: 1 }];
  assert.deepEqual(core.daySegments(week, 0), [
    { zoneId: 1, start: 0, end: 420 },
    { zoneId: 2, start: 420, end: 1440 },
  ]);
  assert.deepEqual(core.daySegments(week, 3), [{ zoneId: 2, start: 0, end: 1440 }]);
  assert.deepEqual(core.daySegments(week, 6), [
    { zoneId: 2, start: 0, end: 1320 },
    { zoneId: 1, start: 1320, end: 1440 },
  ]);
});

test('summary sensors are grouped by home; malformed or foreign states are ignored', () => {
  const parsed = homes({
    'sensor.week': summary(),
    'sensor.other_home': summary({ home_id: 'home-2', home_name: '', schedule_id: 's2' }),
    'sensor.bad_timetable': summary({ schedule_id: 'x', timetable: [{ m_offset: 10080, zone_id: 1 }] }),
    'sensor.duplicate_offsets': summary({
      schedule_id: 'y', timetable: [{ m_offset: 0, zone_id: 1 }, { m_offset: 0, zone_id: 2 }],
    }),
    'sensor.foreign': { state: '3', attributes: { schedule_id: 'z' } },
    'climate.room': summary(),
  });
  assert.deepEqual(parsed.map((home) => [home.id, home.name, home.schedules.length]), [
    ['home-2', 'home-2', 1],
    ['home-1', 'Maison', 1],
  ]);
  const schedule = parsed[1].schedules[0];
  assert.equal(schedule.entityId, 'sensor.week');
  assert.equal(schedule.active, true);
  assert.deepEqual(schedule.model.zones[1].temps, { r1: 20, r2: 19.5 });
  assert.deepEqual(core.parseHomes({ 'sensor.week': summary() }, () => false), []);
});

test('cloud names stay plain data, never markup', () => {
  const name = '<img src=x onerror="alert(1)">';
  const [home] = homes({ 'sensor.week': summary({
    zones: [{ id: 1, name, type: 0, room_temperatures: { r1: 18 } }],
  }) });
  assert.equal(home.schedules[0].model.zones[0].name, name);
});

test('a complete save is one sync_schedule plus one call per changed room', async () => {
  const [home] = homes({ 'sensor.week': summary() });
  const baseline = home.schedules[0].model;
  const edited = core.cloneModel(baseline);
  edited.timetable = core.replaceInterval(edited.timetable, 480, 600, 1);
  edited.hgTemp = 7.5;
  edited.zones[1].temps.r1 = 21.5;
  const calls = [];
  const outcome = await core.saveSchedule(
    { homeId: 'home-1', scheduleId: 'sched-1', scheduleName: 'Semaine', rooms: home.rooms },
    baseline, edited,
    async (service, data) => { calls.push([service, data]); },
  );
  assert.deepEqual(calls, [
    ['sync_schedule', {
      home_id: 'home-1', schedule_id: 'sched-1', timetable: edited.timetable, hg_temp: 7.5,
    }],
    ['set_zone_temperature', {
      home_id: 'home-1', schedule_name: 'Semaine', zone_name: 'Confort', room_name: 'Salon',
      temperature: 21.5,
    }],
  ]);
  assert.equal(outcome.complete, true);
  assert.ok(core.sameModel(outcome.confirmed, edited));
});

test('a failed temperature after a confirmed change leaves only it unsaved', async () => {
  const [home] = homes({ 'sensor.week': summary() });
  const baseline = home.schedules[0].model;
  const edited = core.cloneModel(baseline);
  edited.zones[0].temps.r1 = 17.5;
  edited.zones[1].temps.r2 = 20;
  const outcome = await core.saveSchedule(
    { homeId: 'home-1', scheduleId: 'sched-1', scheduleName: 'Semaine', rooms: home.rooms },
    baseline, edited,
    async (service, data) => {
      if (data.room_name === 'Chambre') {
        throw { code: 'service_validation_error', message: 'Cloud refused' };
      }
    },
  );
  assert.equal(outcome.complete, false);
  assert.deepEqual(outcome.results.map((r) => [r.ok, r.error]), [
    [true, undefined],
    [false, 'Cloud refused'],
  ]);
  assert.equal(outcome.confirmed.zones[0].temps.r1, 17.5);
  assert.equal(outcome.confirmed.zones[1].temps.r2, 19.5);
  const remaining = core.planChanges(outcome.confirmed, edited);
  assert.equal(remaining.sync, null);
  assert.deepEqual(remaining.temperatures.map((t) => [t.roomId, t.temperature]), [['r2', 20]]);
});

test('a failed sync keeps the timetable unsaved while later rooms may succeed', async () => {
  const [home] = homes({ 'sensor.week': summary() });
  const baseline = home.schedules[0].model;
  const edited = core.cloneModel(baseline);
  edited.awayTemp = 15;
  edited.zones[0].temps.r2 = 15;
  const outcome = await core.saveSchedule(
    { homeId: 'home-1', scheduleId: 'sched-1', scheduleName: 'Semaine', rooms: home.rooms },
    baseline, edited,
    async (service) => { if (service === 'sync_schedule') throw new Error('offline'); },
  );
  assert.deepEqual(outcome.results.map((r) => r.ok), [false, true]);
  assert.equal(outcome.confirmed.awayTemp, 16);
  assert.equal(outcome.confirmed.zones[0].temps.r2, 15);
});

test('remote updates never overwrite unsaved edits and stale states are ignored', () => {
  const [home] = homes({ 'sensor.week': summary() });
  const remote = home.schedules[0].model;
  const clean = { baseline: core.cloneModel(remote), edited: core.cloneModel(remote), pending: null };
  const changed = core.cloneModel(remote);
  changed.awayTemp = 18;

  const followed = core.reconcileRemote(clean, changed, 0);
  assert.equal(followed.edited.awayTemp, 18);
  assert.equal(followed.remoteChanged, false);

  const dirty = { ...clean, edited: core.cloneModel(remote) };
  dirty.edited.hgTemp = 8;
  const kept = core.reconcileRemote(dirty, changed, 0);
  assert.equal(kept.edited, dirty.edited);
  assert.equal(kept.remoteChanged, true);

  const saved = core.cloneModel(remote);
  saved.hgTemp = 8;
  saved.zones[0].temps.r1 = 18;
  const waiting = {
    baseline: saved, edited: core.cloneModel(saved), pending: { stale: remote, model: saved, until: 100 },
  };
  // The previous state, or an intermediate one, is ignored while publishing.
  assert.equal(core.reconcileRemote(waiting, remote, 50).edited.hgTemp, 8);
  const intermediate = core.cloneModel(remote);
  intermediate.hgTemp = 8;
  assert.equal(core.reconcileRemote(waiting, intermediate, 50).edited.zones[0].temps.r1, 18);
  assert.equal(core.reconcileRemote(waiting, saved, 50).pending, null);
  assert.equal(core.reconcileRemote(waiting, remote, 150).edited.hgTemp, 7);
  // A value that is neither previous nor confirmed is an outside change.
  const outside = core.cloneModel(saved);
  outside.awayTemp = 12;
  assert.equal(core.reconcileRemote(waiting, outside, 50).edited.awayTemp, 12);
  const dirtyWaiting = { ...waiting, edited: core.cloneModel(saved) };
  dirtyWaiting.edited.awayTemp = 19;
  const flagged = core.reconcileRemote(dirtyWaiting, outside, 50);
  assert.deepEqual([flagged.remoteChanged, flagged.pending, flagged.edited.awayTemp], [true, null, 19]);
});

test('ambiguous names block room edits before any call', () => {
  const [home] = homes({ 'sensor.week': summary({ room_names: { r1: 'Salon', r2: 'SALON' } }) });
  const schedule = home.schedules[0];
  const zone = schedule.model.zones[0];
  assert.deepEqual(core.temperatureBlockers(home, schedule, zone, 'r1'),
    ['plusieurs pièces portent le nom « Salon »']);
  const edited = core.cloneModel(schedule.model);
  edited.zones[0].temps.r1 = 18;
  assert.equal(core.validationErrors(home, schedule, schedule.model, edited).length, 1);

  const sameNames = homes({
    'sensor.a': summary(),
    'sensor.b': summary({ schedule_id: 'sched-2' }),
  })[0];
  assert.match(core.temperatureBlockers(sameNames, sameNames.schedules[0],
    sameNames.schedules[0].model.zones[0], 'r1')[0], /plannings/);
});

test('planning temperatures follow the service ranges and half degrees', () => {
  const [home] = homes({ 'sensor.week': summary() });
  const schedule = home.schedules[0];
  const edited = core.cloneModel(schedule.model);
  edited.awayTemp = 25.5;
  edited.hgTemp = 7.25;
  edited.zones[0].temps.r1 = NaN;
  assert.equal(core.validationErrors(home, schedule, schedule.model, edited).length, 3);
  edited.awayTemp = 25;
  edited.hgTemp = 15;
  edited.zones[0].temps.r1 = 30;
  assert.deepEqual(core.validationErrors(home, schedule, schedule.model, edited), []);
});

test('only plain http(s) Home Assistant addresses are accepted', () => {
  assert.equal(core.normalizeBaseUrl(' http://ha.local:8123/ '), 'http://ha.local:8123');
  assert.equal(core.normalizeBaseUrl('https://example.org/ha/'), 'https://example.org/ha');
  for (const value of [
    'javascript:alert(1)', 'ftp://ha.local', 'http://user:pass@ha.local',
    'http://ha.local/?token=x', 'http://ha.local/#token', 'ha.local',
  ]) {
    assert.throws(() => core.normalizeBaseUrl(value), Error, value);
  }
});
