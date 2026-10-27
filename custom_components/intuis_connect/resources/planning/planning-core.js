/*
 * Intuis planning editor — pure logic, without DOM or network access.
 *
 * Adapted from TheFab21's planning editor (intuis_planning.html, PRs #17, #22
 * and #24 of antoine-pyre/intuis-connect). Interval and midnight rules mirror
 * timetable.py so the editor previews exactly what the services will accept.
 */
(function (root, factory) {
  'use strict';
  var core = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = core;
  } else {
    root.IntuisPlanningCore = core;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var MINUTES_PER_DAY = 1440;
  var MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY;
  var TEMPERATURE_LIMITS = {
    room: { min: 5, max: 30 },
    away: { min: 5, max: 25 },
    hg: { min: 5, max: 15 }
  };

  function isOffset(value) {
    return Number.isInteger(value) && value >= 0 && value < MINUTES_PER_WEEK;
  }

  function mod(value, divisor) {
    return ((value % divisor) + divisor) % divisor;
  }

  function byOffset(a, b) {
    return a.m_offset - b.m_offset;
  }

  function copyTimetable(timetable) {
    return timetable.map(function (row) {
      return { m_offset: row.m_offset, zone_id: row.zone_id };
    }).sort(byOffset);
  }

  /* Zone active at an offset; before the first transition the week wraps. */
  function zoneAt(timetable, offset) {
    var sorted = copyTimetable(timetable);
    if (!sorted.length) {
      return null;
    }
    var zone = sorted[sorted.length - 1].zone_id;
    for (var i = 0; i < sorted.length && sorted[i].m_offset <= offset; i++) {
      zone = sorted[i].zone_id;
    }
    return zone;
  }

  function removeConsecutiveDuplicates(timetable) {
    var result = [];
    copyTimetable(timetable).forEach(function (row) {
      if (!result.length || result[result.length - 1].zone_id !== row.zone_id) {
        result.push(row);
      }
    });
    return result;
  }

  function upsert(timetable, offset, zoneId) {
    for (var i = 0; i < timetable.length; i++) {
      if (timetable[i].m_offset === offset) {
        timetable[i].zone_id = zoneId;
        return;
      }
    }
    timetable.push({ m_offset: offset, zone_id: zoneId });
  }

  /* Replace [start, end) of the cyclic week; the complement is unchanged. */
  function replaceInterval(timetable, start, end, zoneId) {
    if (!isOffset(start) || !Number.isInteger(end) || end < 0 || end > MINUTES_PER_WEEK) {
      throw new Error('Les bornes doivent être des minutes entières de la semaine.');
    }
    var normalizedEnd = end % MINUTES_PER_WEEK;
    var duration = mod(normalizedEnd - start, MINUTES_PER_WEEK);
    if (!duration) {
      throw new Error('Le début et la fin du créneau doivent être différents.');
    }
    if (!timetable.length) {
      throw new Error('Ce planning ne contient aucune transition.');
    }
    var original = copyTimetable(timetable);
    var restoreZone = zoneAt(original, normalizedEnd);
    var updated = original.filter(function (row) {
      return mod(row.m_offset - start, MINUTES_PER_WEEK) >= duration;
    });
    upsert(updated, start, zoneId);
    upsert(updated, normalizedEnd, restoreZone);
    return removeConsecutiveDuplicates(updated);
  }

  function parseClock(value) {
    var match = /^(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(String(value));
    if (!match) {
      throw new Error('Heure invalide : utilisez HH:MM.');
    }
    var hours = Number(match[1]);
    var minutes = Number(match[2]);
    var seconds = match[3] === undefined ? 0 : Number(match[3]);
    if (hours > 23 || minutes > 59 || seconds !== 0) {
      throw new Error('Heure invalide : utilisez HH:MM, sans secondes.');
    }
    return [hours, minutes];
  }

  function parseDay(value) {
    var day = Number(value);
    if (String(value) === '' || !Number.isInteger(day) || day < 0 || day > 6) {
      throw new Error('Jour invalide.');
    }
    return day;
  }

  /*
   * Same rules as schedule_slot_offsets: on the same day an end of 00:00 is the
   * following midnight; on another day it is the start of that day.
   */
  function slotOffsets(startDay, startTime, endDay, endTime) {
    var first = parseDay(startDay);
    var last = parseDay(endDay);
    var startClock = parseClock(startTime);
    var endClock = parseClock(endTime);
    var start = first * MINUTES_PER_DAY + startClock[0] * 60 + startClock[1];
    var end = last * MINUTES_PER_DAY + endClock[0] * 60 + endClock[1];
    if (first === last && endClock[0] === 0 && endClock[1] === 0) {
      end = (last + 1) * MINUTES_PER_DAY;
    }
    if (first === last && end <= start) {
      throw new Error('Le même jour, la fin doit suivre le début.');
    }
    if (start % MINUTES_PER_WEEK === end % MINUTES_PER_WEEK) {
      throw new Error('Le début et la fin du créneau doivent être différents.');
    }
    return [start, end];
  }

  /* Merged segments of one day, inheriting the zone active at its midnight. */
  function daySegments(timetable, day) {
    var base = day * MINUTES_PER_DAY;
    var segments = [];
    var zone = zoneAt(timetable, base);
    if (zone === null) {
      return segments;
    }
    var cursor = 0;
    copyTimetable(timetable).forEach(function (row) {
      var at = row.m_offset - base;
      if (at < 0 || at >= MINUTES_PER_DAY) {
        return;
      }
      if (at > cursor) {
        segments.push({ zoneId: zone, start: cursor, end: at });
      }
      zone = row.zone_id;
      cursor = at;
    });
    segments.push({ zoneId: zone, start: cursor, end: MINUTES_PER_DAY });
    return segments.reduce(function (merged, segment) {
      var previous = merged[merged.length - 1];
      if (previous && previous.zoneId === segment.zoneId) {
        previous.end = segment.end;
      } else {
        merged.push(segment);
      }
      return merged;
    }, []);
  }

  function formatClock(minutes) {
    var hours = Math.floor(minutes / 60);
    var rest = minutes % 60;
    return (hours < 10 ? '0' : '') + hours + ':' + (rest < 10 ? '0' : '') + rest;
  }

  function isHalfDegree(value, limits) {
    return typeof value === 'number' && isFinite(value)
      && value >= limits.min && value <= limits.max
      && Number.isInteger(value * 2);
  }

  function isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function parseTimetable(rows) {
    if (!Array.isArray(rows) || !rows.length) {
      return null;
    }
    var seen = {};
    var result = [];
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if (!isPlainObject(row) || !isOffset(row.m_offset) || !Number.isInteger(row.zone_id)
          || seen[row.m_offset]) {
        return null;
      }
      seen[row.m_offset] = true;
      result.push({ m_offset: row.m_offset, zone_id: row.zone_id });
    }
    return result.sort(byOffset);
  }

  function parseZones(rows) {
    if (!Array.isArray(rows)) {
      return null;
    }
    var zones = [];
    for (var i = 0; i < rows.length; i++) {
      var zone = rows[i];
      if (!isPlainObject(zone) || !Number.isInteger(zone.id) || typeof zone.name !== 'string') {
        return null;
      }
      var temps = {};
      var source = isPlainObject(zone.room_temperatures) ? zone.room_temperatures : {};
      Object.keys(source).forEach(function (roomId) {
        if (typeof source[roomId] === 'number' && isFinite(source[roomId])) {
          temps[roomId] = source[roomId];
        }
      });
      zones.push({ id: zone.id, name: zone.name, type: zone.type, temps: temps });
    }
    return zones;
  }

  function optionalNumber(value) {
    return typeof value === 'number' && isFinite(value) ? value : null;
  }

  /*
   * Read the schedule summary sensors (one per schedule) from an entity_id ->
   * state map. Malformed or foreign states are ignored rather than guessed.
   */
  function parseHomes(states, accept) {
    var homes = {};
    Object.keys(states || {}).forEach(function (entityId) {
      var state = states[entityId];
      var attrs = state && state.attributes;
      if (entityId.indexOf('sensor.') !== 0 || !isPlainObject(attrs)
          || (accept && !accept(entityId))
          || typeof attrs.schedule_id !== 'string' || typeof attrs.home_id !== 'string'
          || !isPlainObject(attrs.room_names)) {
        return;
      }
      var timetable = parseTimetable(attrs.timetable);
      var zones = parseZones(attrs.zones);
      if (!timetable || !zones || !zones.length) {
        return;
      }
      var home = homes[attrs.home_id];
      if (!home) {
        home = homes[attrs.home_id] = {
          id: attrs.home_id,
          name: typeof attrs.home_name === 'string' && attrs.home_name ? attrs.home_name : attrs.home_id,
          rooms: {},
          schedules: []
        };
      }
      Object.keys(attrs.room_names).forEach(function (roomId) {
        if (typeof attrs.room_names[roomId] === 'string') {
          home.rooms[roomId] = attrs.room_names[roomId];
        }
      });
      home.schedules.push({
        entityId: entityId,
        id: attrs.schedule_id,
        name: typeof state.state === 'string' ? state.state : attrs.schedule_id,
        active: attrs.is_active === true,
        model: {
          timetable: timetable,
          awayTemp: optionalNumber(attrs.away_temperature),
          hgTemp: optionalNumber(attrs.frost_guard_temperature),
          zones: zones
        }
      });
    });
    return Object.keys(homes).map(function (id) {
      homes[id].schedules.sort(function (a, b) {
        return a.name.localeCompare(b.name) || a.id.localeCompare(b.id);
      });
      return homes[id];
    }).sort(function (a, b) {
      return a.name.localeCompare(b.name) || a.id.localeCompare(b.id);
    });
  }

  function cloneModel(model) {
    return {
      timetable: copyTimetable(model.timetable),
      awayTemp: model.awayTemp,
      hgTemp: model.hgTemp,
      zones: model.zones.map(function (zone) {
        var temps = {};
        Object.keys(zone.temps).forEach(function (roomId) {
          temps[roomId] = zone.temps[roomId];
        });
        return { id: zone.id, name: zone.name, type: zone.type, temps: temps };
      })
    };
  }

  function canonical(model) {
    return JSON.stringify([
      copyTimetable(model.timetable),
      model.awayTemp,
      model.hgTemp,
      model.zones.map(function (zone) {
        return [zone.id, zone.name, Object.keys(zone.temps).sort().map(function (roomId) {
          return [roomId, zone.temps[roomId]];
        })];
      })
    ]);
  }

  function sameModel(a, b) {
    return canonical(a) === canonical(b);
  }

  function sameTimetable(a, b) {
    return JSON.stringify(copyTimetable(a)) === JSON.stringify(copyTimetable(b));
  }

  /* One atomic sync_schedule plus one confirmed call per changed room. */
  function planChanges(baseline, edited) {
    var sync = {};
    if (!sameTimetable(baseline.timetable, edited.timetable)) {
      sync.timetable = copyTimetable(edited.timetable);
    }
    if (edited.awayTemp !== baseline.awayTemp) {
      sync.away_temp = edited.awayTemp;
    }
    if (edited.hgTemp !== baseline.hgTemp) {
      sync.hg_temp = edited.hgTemp;
    }
    var temperatures = [];
    edited.zones.forEach(function (zone) {
      var before = baseline.zones.filter(function (z) { return z.id === zone.id; })[0];
      Object.keys(zone.temps).forEach(function (roomId) {
        if (!before || before.temps[roomId] !== zone.temps[roomId]) {
          temperatures.push({
            zoneId: zone.id,
            zoneName: zone.name,
            roomId: roomId,
            temperature: zone.temps[roomId]
          });
        }
      });
    });
    return { sync: Object.keys(sync).length ? sync : null, temperatures: temperatures };
  }

  /*
   * set_zone_temperature addresses the schedule, zone and room by their IDs,
   * so duplicate names never redirect an edit. Only a room the home no longer
   * knows is refused before any call.
   */
  function temperatureBlockers(home, schedule, zone, roomId) {
    var reasons = [];
    if (!Object.prototype.hasOwnProperty.call(home.rooms, roomId)) {
      reasons.push('pièce inconnue');
    }
    return reasons;
  }

  function validationErrors(home, schedule, baseline, edited) {
    var errors = [];
    if (edited.awayTemp !== baseline.awayTemp && !isHalfDegree(edited.awayTemp, TEMPERATURE_LIMITS.away)) {
      errors.push('Absence : de 5 à 25 °C par pas de 0,5 °C.');
    }
    if (edited.hgTemp !== baseline.hgTemp && !isHalfDegree(edited.hgTemp, TEMPERATURE_LIMITS.hg)) {
      errors.push('Hors-gel : de 5 à 15 °C par pas de 0,5 °C.');
    }
    planChanges(baseline, edited).temperatures.forEach(function (change) {
      var zone = edited.zones.filter(function (z) { return z.id === change.zoneId; })[0];
      var label = (home.rooms[change.roomId] || change.roomId) + ' (' + change.zoneName + ')';
      if (!isHalfDegree(change.temperature, TEMPERATURE_LIMITS.room)) {
        errors.push(label + ' : de 5 à 30 °C par pas de 0,5 °C.');
      }
      temperatureBlockers(home, schedule, zone, change.roomId).forEach(function (reason) {
        errors.push(label + ' : modification impossible, ' + reason + '.');
      });
    });
    return errors;
  }

  function errorMessage(error) {
    if (error && typeof error.message === 'string' && error.message) {
      return error.message;
    }
    if (error && typeof error.error === 'string') {
      return error.error;
    }
    return 'Erreur inconnue';
  }

  function formatTemperature(value) {
    return String(value).replace('.', ',') + ' °C';
  }

  function describeSync(sync) {
    var parts = [];
    if (sync.timetable) {
      parts.push('horaires');
    }
    if (sync.away_temp !== undefined) {
      parts.push('absence ' + formatTemperature(sync.away_temp));
    }
    if (sync.hg_temp !== undefined) {
      parts.push('hors-gel ' + formatTemperature(sync.hg_temp));
    }
    return 'Planning : ' + parts.join(', ');
  }

  /*
   * Run the save sequence. Each step is reported separately and only steps
   * acknowledged by Home Assistant enter the returned confirmed model; there
   * is no global transaction across several service calls.
   */
  function saveSchedule(target, baseline, edited, callService) {
    var plan = planChanges(baseline, edited);
    var confirmed = cloneModel(baseline);
    var results = [];
    var steps = [];
    if (plan.sync) {
      steps.push(function () {
        var data = { home_id: target.homeId, schedule_id: target.scheduleId };
        Object.keys(plan.sync).forEach(function (key) { data[key] = plan.sync[key]; });
        return callService('sync_schedule', data).then(function () {
          if (plan.sync.timetable) {
            confirmed.timetable = copyTimetable(plan.sync.timetable);
          }
          if (plan.sync.away_temp !== undefined) {
            confirmed.awayTemp = plan.sync.away_temp;
          }
          if (plan.sync.hg_temp !== undefined) {
            confirmed.hgTemp = plan.sync.hg_temp;
          }
          results.push({ label: describeSync(plan.sync), ok: true });
        }, function (error) {
          results.push({ label: describeSync(plan.sync), ok: false, error: errorMessage(error) });
        });
      });
    }
    plan.temperatures.forEach(function (change) {
      var roomName = target.rooms[change.roomId] || change.roomId;
      var label = roomName + ' — ' + change.zoneName + ' : ' + formatTemperature(change.temperature);
      steps.push(function () {
        return callService('set_zone_temperature', {
          home_id: target.homeId,
          schedule_id: target.scheduleId,
          zone_id: change.zoneId,
          room_id: change.roomId,
          temperature: change.temperature
        }).then(function () {
          confirmed.zones.forEach(function (zone) {
            if (zone.id === change.zoneId) {
              zone.temps[change.roomId] = change.temperature;
            }
          });
          results.push({ label: label, ok: true });
        }, function (error) {
          results.push({ label: label, ok: false, error: errorMessage(error) });
        });
      });
    });
    return steps.reduce(function (chain, step) {
      return chain.then(step);
    }, Promise.resolve()).then(function () {
      return {
        results: results,
        confirmed: confirmed,
        complete: results.every(function (result) { return result.ok; })
      };
    });
  }

  /*
   * While a save is being published, Home Assistant may still show the previous
   * state, or an intermediate one between two service calls. Such a state only
   * combines pre-save and confirmed values; anything else is an outside change.
   */
  function isTransition(remote, stale, confirmed) {
    function either(value, before, after) {
      return value === before || value === after;
    }
    if (!sameTimetable(remote.timetable, stale.timetable)
        && !sameTimetable(remote.timetable, confirmed.timetable)) {
      return false;
    }
    if (!either(remote.awayTemp, stale.awayTemp, confirmed.awayTemp)
        || !either(remote.hgTemp, stale.hgTemp, confirmed.hgTemp)
        || remote.zones.length !== confirmed.zones.length) {
      return false;
    }
    return remote.zones.every(function (zone, index) {
      var before = stale.zones[index];
      var after = confirmed.zones[index];
      var rooms = Object.keys(zone.temps);
      return before && after && zone.id === after.id && zone.name === after.name
        && rooms.length === Object.keys(after.temps).length
        && rooms.every(function (roomId) {
          return either(zone.temps[roomId], before.temps[roomId], after.temps[roomId]);
        });
    });
  }

  /*
   * Merge a remote model into the editor. Unsaved edits are never overwritten.
   * editor.pending = {stale, model, until} after a save: transition states are
   * ignored until the confirmed model appears or the wait expires.
   */
  function reconcileRemote(editor, remote, now) {
    var pending = editor.pending;
    if (pending && !sameModel(remote, pending.model) && now < pending.until
        && isTransition(remote, pending.stale, pending.model)) {
      return { baseline: editor.baseline, edited: editor.edited, pending: pending, remoteChanged: false };
    }
    if (sameModel(editor.baseline, editor.edited)) {
      return { baseline: cloneModel(remote), edited: cloneModel(remote), pending: null, remoteChanged: false };
    }
    return {
      baseline: editor.baseline,
      edited: editor.edited,
      pending: null,
      remoteChanged: !sameModel(remote, editor.baseline)
    };
  }

  /* Validate the Home Assistant address typed for standalone use. */
  function normalizeBaseUrl(value) {
    var url;
    try {
      url = new URL(String(value).trim());
    } catch (error) {
      throw new Error('Adresse invalide.');
    }
    if ((url.protocol !== 'http:' && url.protocol !== 'https:') || url.username || url.password
        || url.search || url.hash) {
      throw new Error('Utilisez une adresse http(s) sans identifiants, paramètres ni fragment.');
    }
    return url.origin + url.pathname.replace(/\/+$/, '');
  }

  return {
    MINUTES_PER_DAY: MINUTES_PER_DAY,
    MINUTES_PER_WEEK: MINUTES_PER_WEEK,
    TEMPERATURE_LIMITS: TEMPERATURE_LIMITS,
    cloneModel: cloneModel,
    daySegments: daySegments,
    errorMessage: errorMessage,
    formatClock: formatClock,
    formatTemperature: formatTemperature,
    isHalfDegree: isHalfDegree,
    normalizeBaseUrl: normalizeBaseUrl,
    parseHomes: parseHomes,
    planChanges: planChanges,
    reconcileRemote: reconcileRemote,
    replaceInterval: replaceInterval,
    sameModel: sameModel,
    saveSchedule: saveSchedule,
    slotOffsets: slotOffsets,
    temperatureBlockers: temperatureBlockers,
    validationErrors: validationErrors,
    zoneAt: zoneAt
  };
});
