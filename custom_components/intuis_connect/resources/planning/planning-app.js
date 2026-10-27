/*
 * Intuis planning editor — user interface and Home Assistant connections.
 *
 * Adapted from TheFab21's planning editor (PRs #17, #22 and #24 of
 * antoine-pyre/intuis-connect). Cloud values are always rendered as text.
 */
(function () {
  'use strict';

  var core = window.IntuisPlanningCore;
  var DOMAIN = 'intuis_connect';
  var CONNECT_WAIT_MS = 45000;
  var CONFIRMATION_WAIT_MS = 20000;
  var FOLLOW_UP_POLLS_MS = [3000, 8000, 15000];
  var COLORS = ['#ef5350', '#42a5f5', '#ffca28', '#66bb6a', '#ab47bc',
    '#26a69a', '#8d6e63', '#78909c', '#ec407a', '#5c6bc0'];
  var DAYS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
  var DAYS_FULL = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];
  var STORAGE_URL = 'intuis_planning_url';
  var STORAGE_TOKEN = 'intuis_planning_token';
  // Keys written by earlier manual copies of the editor; cleared on logout.
  var LEGACY_TOKEN_KEYS = ['intuis_ha_token_saved', 'intuis_ha_token'];
  var UNSAVED_PROMPT = 'Des modifications non enregistrées seront perdues. Continuer ?';

  function $(id) {
    return document.getElementById(id);
  }

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text !== undefined) {
      node.textContent = text;
    }
    return node;
  }

  function clear(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function storage(kind) {
    try {
      return window[kind];
    } catch (error) {
      return null;
    }
  }

  function storageGet(kind, key) {
    try {
      var store = storage(kind);
      return store ? store.getItem(key) : null;
    } catch (error) {
      return null;
    }
  }

  function storageSet(kind, key, value) {
    try {
      var store = storage(kind);
      if (store) {
        store.setItem(key, value);
      }
    } catch (error) {
      // Private browsing: the value simply stays in memory.
    }
  }

  function storageRemove(kind, key) {
    try {
      var store = storage(kind);
      if (store) {
        store.removeItem(key);
      }
    } catch (error) {
      // Nothing stored.
    }
  }

  function delay(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  /* ---------- Connections: one contract for the iframe and the REST API ---------- */

  function parentHomeAssistant() {
    try {
      if (window.parent && window.parent !== window) {
        return window.parent.document.querySelector('home-assistant');
      }
    } catch (error) {
      // Cross-origin parent: not a Home Assistant dashboard.
    }
    return null;
  }

  function IframeConnection(host) {
    this.mode = 'iframe';
    this.host = host;
    this.pollInterval = 2000;
  }
  IframeConnection.prototype.hass = function () {
    return this.host.hass || null;
  };
  IframeConnection.prototype.ready = function () {
    var hass = this.hass();
    return Boolean(hass && hass.states && hass.connected !== false
      && hass.callService && Object.keys(hass.states).length);
  };
  IframeConnection.prototype.connected = function () {
    var hass = this.hass();
    return Boolean(hass && hass.connected !== false);
  };
  IframeConnection.prototype.getStates = function () {
    var hass = this.hass();
    return hass && hass.states ? Promise.resolve(hass.states)
      : Promise.reject(new Error('Home Assistant est indisponible.'));
  };
  IframeConnection.prototype.accept = function (entityId) {
    var hass = this.hass();
    var entry = hass && hass.entities && hass.entities[entityId];
    return !entry || entry.platform === undefined || entry.platform === DOMAIN;
  };
  IframeConnection.prototype.callService = function (service, data) {
    // notifyOnError=false: errors are shown by the editor, not as a parent toast.
    return Promise.resolve(this.hass().callService(DOMAIN, service, data, undefined, false));
  };
  IframeConnection.prototype.darkMode = function () {
    var hass = this.hass();
    return hass && hass.themes && typeof hass.themes.darkMode === 'boolean'
      ? hass.themes.darkMode : null;
  };

  function RestConnection(baseUrl, token) {
    this.mode = 'rest';
    this.baseUrl = baseUrl;
    this.token = token;
    this.pollInterval = 30000;
    this.lastFailure = null;
  }
  RestConnection.prototype.request = function (path, body) {
    var self = this;
    var options = {
      method: body === undefined ? 'GET' : 'POST',
      headers: { Authorization: 'Bearer ' + this.token, 'Content-Type': 'application/json' },
      credentials: 'omit',
      cache: 'no-store',
      referrerPolicy: 'no-referrer'
    };
    if (body !== undefined) {
      options.body = JSON.stringify(body);
    }
    return fetch(this.baseUrl + path, options).then(function (response) {
      self.lastFailure = null;
      if (response.ok) {
        return response.json();
      }
      return response.text().then(function (text) {
        var message = '';
        try {
          var parsed = JSON.parse(text);
          message = parsed && typeof parsed.message === 'string' ? parsed.message : '';
        } catch (error) {
          // HA 2024.6 answers some service errors with a plain-text 500 page.
          message = '';
        }
        throw httpError(response.status, message);
      });
    }, function () {
      var error = new Error('Home Assistant est injoignable à cette adresse.');
      error.network = true;
      self.lastFailure = error;
      throw error;
    });
  };
  RestConnection.prototype.ready = function () {
    return true;
  };
  RestConnection.prototype.connected = function () {
    return this.lastFailure === null;
  };
  RestConnection.prototype.getStates = function () {
    return this.request('/api/states').then(function (list) {
      var states = {};
      (Array.isArray(list) ? list : []).forEach(function (state) {
        if (state && typeof state.entity_id === 'string') {
          states[state.entity_id] = state;
        }
      });
      return states;
    });
  };
  RestConnection.prototype.accept = null;
  RestConnection.prototype.callService = function (service, data) {
    return this.request('/api/services/' + DOMAIN + '/' + service, data);
  };
  RestConnection.prototype.darkMode = function () {
    return null;
  };

  function httpError(status, message) {
    var text = String(message || '').slice(0, 300);
    var error;
    if (status === 401 || status === 403) {
      error = new Error('Token refusé par Home Assistant (HTTP ' + status + ').');
      error.auth = true;
    } else {
      error = new Error(text || 'Requête refusée (HTTP ' + status + ').');
    }
    error.status = status;
    return error;
  }

  function retryable(error) {
    return Boolean(error && (error.network || error.status >= 500));
  }

  /* Retry transient failures with backoff, for at most CONNECT_WAIT_MS. */
  function withBoundedRetry(task, onWait) {
    var deadline = Date.now() + CONNECT_WAIT_MS;
    var wait = 1000;
    function attempt() {
      return task().catch(function (error) {
        var remaining = deadline - Date.now();
        if (!retryable(error) || remaining <= 0) {
          throw error;
        }
        onWait(Math.ceil(remaining / 1000));
        var pause = Math.min(wait, remaining);
        wait = Math.min(wait * 2, 8000);
        return delay(pause).then(attempt);
      });
    }
    return attempt();
  }

  /* ---------- State ---------- */

  var state = {
    conn: null,
    homes: [],
    homeId: null,
    entityId: null,
    editor: null,
    signature: null,
    saving: false,
    missing: false,
    timer: null
  };

  function currentHome() {
    return state.homes.filter(function (home) { return home.id === state.homeId; })[0] || null;
  }

  function currentSchedule() {
    var home = currentHome();
    return home && home.schedules.filter(function (s) { return s.entityId === state.entityId; })[0] || null;
  }

  function isDirty() {
    return Boolean(state.editor && !core.sameModel(state.editor.baseline, state.editor.edited));
  }

  function newEditor(model) {
    return { baseline: core.cloneModel(model), edited: core.cloneModel(model), pending: null, remoteChanged: false };
  }

  /* ---------- Screens ---------- */

  function showScreen(id) {
    ['loading', 'failure', 'setup', 'app'].forEach(function (name) {
      $(name).hidden = name !== id;
    });
  }

  function showLoading(text) {
    $('loading-text').textContent = text;
    showScreen('loading');
  }

  var toastTimer = null;
  function toast(message) {
    var node = $('toast');
    node.textContent = message;
    node.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { node.hidden = true; }, 3500);
  }

  function showFailure(message, retry) {
    stopPolling();
    $('failure-text').textContent = message;
    $('failure-retry').onclick = retry;
    showScreen('failure');
  }

  function showSetup(message) {
    stopPolling();
    state.conn = null;
    $('setup-url').value = storageGet('localStorage', STORAGE_URL) || window.location.origin;
    $('setup-token').value = '';
    $('setup-remember').checked = false;
    $('setup-error').textContent = message || '';
    $('setup-error').hidden = !message;
    showScreen('setup');
  }

  /* ---------- Connection lifecycle ---------- */

  function startIframe(host) {
    stopPolling();
    var connection = new IframeConnection(host);
    var deadline = Date.now() + CONNECT_WAIT_MS;
    showLoading('Connexion à Home Assistant…');
    (function wait() {
      if (connection.ready()) {
        state.conn = connection;
        connection.getStates().then(loadInitial);
        return;
      }
      var remaining = Math.ceil((deadline - Date.now()) / 1000);
      if (remaining <= 0) {
        showFailure('Home Assistant ne répond pas après 45 secondes. Vérifiez qu\'il est démarré.',
          function () { startIframe(host); });
        return;
      }
      $('loading-text').textContent = 'En attente de la reconnexion de Home Assistant… (' + remaining + ' s)';
      setTimeout(wait, 500);
    })();
  }

  function forgetToken() {
    storageRemove('sessionStorage', STORAGE_TOKEN);
    storageRemove('localStorage', STORAGE_TOKEN);
    LEGACY_TOKEN_KEYS.forEach(function (key) {
      storageRemove('sessionStorage', key);
      storageRemove('localStorage', key);
    });
  }

  function connectRest(baseUrl, token, remember) {
    stopPolling();
    var connection = new RestConnection(baseUrl, token);
    showLoading('Connexion à Home Assistant…');
    return withBoundedRetry(function () { return connection.getStates(); }, function (remaining) {
      $('loading-text').textContent = 'Home Assistant injoignable, nouvel essai… (' + remaining + ' s)';
    }).then(function (states) {
      state.conn = connection;
      storageSet('localStorage', STORAGE_URL, baseUrl);
      if (remember === true) {
        storageSet('localStorage', STORAGE_TOKEN, token);
        storageRemove('sessionStorage', STORAGE_TOKEN);
      } else if (remember === false) {
        storageSet('sessionStorage', STORAGE_TOKEN, token);
        storageRemove('localStorage', STORAGE_TOKEN);
      }
      loadInitial(states);
    }, function (error) {
      if (error.auth) {
        forgetToken();
        showSetup(error.message);
      } else {
        showFailure(error.message, function () { connectRest(baseUrl, token, remember); });
      }
    });
  }

  function startStandalone() {
    var token = storageGet('sessionStorage', STORAGE_TOKEN) || storageGet('localStorage', STORAGE_TOKEN);
    var baseUrl = storageGet('localStorage', STORAGE_URL);
    if (token && baseUrl) {
      connectRest(baseUrl, token, undefined);
    } else {
      showSetup();
    }
  }

  function start() {
    var host = parentHomeAssistant();
    if (host) {
      startIframe(host);
    } else {
      startStandalone();
    }
  }

  function stopPolling() {
    if (state.timer) {
      clearInterval(state.timer);
      state.timer = null;
    }
  }

  function startPolling() {
    stopPolling();
    state.timer = setInterval(poll, state.conn.pollInterval);
  }

  function poll() {
    var connection = state.conn;
    if (!connection || state.saving || (connection.mode === 'rest' && document.hidden)) {
      return;
    }
    connection.getStates().then(function (states) {
      if (connection === state.conn) {
        applyStates(states);
      }
    }, function (error) {
      if (error.auth && connection === state.conn) {
        forgetToken();
        showSetup(error.message);
        return;
      }
      updateConnectionStatus();
    });
  }

  function loadInitial(states) {
    state.editor = null;
    state.signature = null;
    $('logout').hidden = state.conn.mode !== 'rest';
    showScreen('app');
    applyStates(states);
    startPolling();
  }

  /* ---------- Data ---------- */

  function chooseSelection() {
    var home = currentHome() || state.homes[0] || null;
    state.homeId = home ? home.id : null;
    if (!home) {
      state.entityId = null;
      return;
    }
    var schedule = currentSchedule()
      || home.schedules.filter(function (s) { return s.active; })[0]
      || home.schedules[0];
    state.entityId = schedule.entityId;
  }

  function applyStates(states) {
    var accept = state.conn.accept ? state.conn.accept.bind(state.conn) : null;
    var homes = core.parseHomes(states, accept);
    var signature = JSON.stringify(homes);
    updateConnectionStatus();
    if (signature === state.signature && !(state.editor && state.editor.pending)) {
      return;
    }
    state.signature = signature;
    var previousEntity = state.entityId;
    state.homes = homes;
    var schedule = currentSchedule();
    if (state.editor && previousEntity && !schedule) {
      // The schedule being edited disappeared from Home Assistant.
      if (isDirty()) {
        state.missing = true;
        renderBanner();
        renderSelectors();
        return;
      }
      state.editor = null;
    }
    state.missing = false;
    chooseSelection();
    schedule = currentSchedule();
    if (!schedule) {
      state.editor = null;
      render();
      return;
    }
    if (!state.editor || schedule.entityId !== previousEntity) {
      state.editor = newEditor(schedule.model);
      render();
      return;
    }
    var before = state.editor;
    state.editor = core.reconcileRemote(before, schedule.model, Date.now());
    if (state.editor.edited !== before.edited) {
      render();
      return;
    }
    // Unsaved edits are kept: refresh only the selectors, banner and buttons.
    renderSelectors();
    renderBanner();
    updateDirtyState();
  }

  function updateConnectionStatus() {
    var connection = state.conn;
    if (!connection) {
      return;
    }
    var online = connection.connected();
    var text = connection.mode === 'iframe' ? 'Session Home Assistant' : 'Connecté à ' + connection.baseUrl;
    $('connection-status').textContent = online ? text : 'Connexion perdue, reconnexion…';
    var dark = connection.darkMode();
    if (dark === null) {
      delete document.documentElement.dataset.theme;
    } else {
      document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    }
    updateDirtyState();
  }

  /* ---------- Rendering ---------- */

  function zoneColor(zoneId) {
    return COLORS[Math.abs(zoneId) % COLORS.length];
  }

  function zoneName(model, zoneId) {
    var zone = model.zones.filter(function (z) { return z.id === zoneId; })[0];
    return zone ? zone.name : 'Zone ' + zoneId;
  }

  function render() {
    renderSelectors();
    renderBanner();
    var schedule = currentSchedule();
    $('empty').hidden = Boolean(schedule);
    $('editor').hidden = !schedule;
    if (!schedule) {
      return;
    }
    renderTemperatures();
    renderWeek();
    renderLegend();
    renderZones();
    updateDirtyState();
  }

  function renderSelectors() {
    var homeSelect = $('home');
    clear(homeSelect);
    state.homes.forEach(function (home) {
      var option = element('option', null, home.name === home.id ? home.id : home.name + ' (' + home.id + ')');
      option.value = home.id;
      homeSelect.appendChild(option);
    });
    homeSelect.value = state.homeId || '';
    $('home-field').hidden = state.homes.length < 2;
    var scheduleSelect = $('schedule');
    clear(scheduleSelect);
    var home = currentHome();
    (home ? home.schedules : []).forEach(function (schedule) {
      var option = element('option', null, schedule.name + (schedule.active ? ' (actif)' : ''));
      option.value = schedule.entityId;
      scheduleSelect.appendChild(option);
    });
    if (state.missing) {
      var gone = element('option', null, 'Planning supprimé');
      gone.value = state.entityId;
      scheduleSelect.appendChild(gone);
    }
    scheduleSelect.value = state.entityId || '';
  }

  function renderBanner() {
    var text = '';
    if (state.missing) {
      text = 'Ce planning n\'existe plus dans Home Assistant ; vos modifications ne peuvent pas être enregistrées.';
    } else if (state.editor && state.editor.remoteChanged) {
      text = 'Ce planning a été modifié en dehors de cet éditeur. Vos modifications non enregistrées sont conservées.';
    }
    $('banner-text').textContent = text;
    $('banner-reload').hidden = !text;
    $('banner').hidden = !text;
  }

  function renderTemperatures() {
    var edited = state.editor.edited;
    $('away').value = edited.awayTemp === null || isNaN(edited.awayTemp) ? '' : edited.awayTemp;
    $('hg').value = edited.hgTemp === null || isNaN(edited.hgTemp) ? '' : edited.hgTemp;
  }

  function hoursRow() {
    var row = element('div', 'hours');
    row.appendChild(element('div', 'day'));
    var scale = element('div', 'scale');
    for (var hour = 0; hour <= 24; hour += 2) {
      var mark = element('span', 'hour' + (hour === 0 ? ' first' : hour === 24 ? ' last' : ''), hour + 'h');
      mark.style.left = (hour / 24 * 100) + '%';
      scale.appendChild(mark);
    }
    row.appendChild(scale);
    row.appendChild(element('div', 'spacer'));
    return row;
  }

  function renderWeek() {
    var week = $('week');
    var model = state.editor.edited;
    clear(week);
    week.appendChild(hoursRow());
    for (var day = 0; day < 7; day++) {
      var row = element('div', 'row');
      row.appendChild(element('div', 'day', DAYS[day]));
      var bar = element('div', 'bar');
      for (var hour = 6; hour < 24; hour += 6) {
        var tick = element('span', 'tick');
        tick.style.left = (hour / 24 * 100) + '%';
        bar.appendChild(tick);
      }
      core.daySegments(model.timetable, day).forEach(function (segment) {
        var name = zoneName(model, segment.zoneId);
        var label = DAYS_FULL[day] + ' ' + core.formatClock(segment.start) + '–'
          + core.formatClock(segment.end) + ' : ' + name;
        var button = element('button', 'seg', segment.end - segment.start >= 120 ? name : '');
        button.type = 'button';
        button.title = label;
        button.setAttribute('aria-label', label);
        button.style.width = ((segment.end - segment.start) / core.MINUTES_PER_DAY * 100) + '%';
        button.style.background = zoneColor(segment.zoneId) + '66';
        button.disabled = state.saving;
        button.onclick = openSlotDialog.bind(null, day, segment);
        bar.appendChild(button);
      });
      row.appendChild(bar);
      var add = element('button', 'add', '+');
      add.type = 'button';
      add.title = 'Ajouter un créneau le ' + DAYS_FULL[day].toLowerCase();
      add.setAttribute('aria-label', add.title);
      add.disabled = state.saving;
      add.onclick = openSlotDialog.bind(null, day, null);
      row.appendChild(add);
      week.appendChild(row);
    }
    week.appendChild(hoursRow());
  }

  function swatch(zoneId) {
    var node = element('i', 'swatch');
    node.style.background = zoneColor(zoneId);
    return node;
  }

  function renderLegend() {
    var legend = $('legend');
    clear(legend);
    state.editor.edited.zones.forEach(function (zone) {
      var item = element('span');
      item.appendChild(swatch(zone.id));
      item.appendChild(document.createTextNode(zone.name));
      legend.appendChild(item);
    });
  }

  function setRoomTemperature(zone, roomId, value) {
    zone.temps[roomId] = value;
    updateDirtyState();
  }

  function renderZones() {
    var container = $('zones');
    var home = currentHome();
    var schedule = currentSchedule();
    clear(container);
    state.editor.edited.zones.forEach(function (zone) {
      var box = element('div', 'zone');
      var title = element('h3');
      title.appendChild(swatch(zone.id));
      title.appendChild(document.createTextNode(zone.name));
      box.appendChild(title);
      Object.keys(zone.temps).sort(function (a, b) {
        return String(home.rooms[a] || a).localeCompare(String(home.rooms[b] || b));
      }).forEach(function (roomId) {
        var row = element('div', 'temp');
        var roomName = home.rooms[roomId] || roomId;
        var room = element('span', 'room', roomName);
        room.title = roomName;
        var input = element('input');
        input.type = 'number';
        input.min = core.TEMPERATURE_LIMITS.room.min;
        input.max = core.TEMPERATURE_LIMITS.room.max;
        input.step = '0.5';
        input.inputMode = 'decimal';
        input.value = zone.temps[roomId];
        input.setAttribute('aria-label', roomName + ', ' + zone.name);
        var minus = element('button', null, '−');
        var plus = element('button', null, '+');
        minus.type = plus.type = 'button';
        minus.setAttribute('aria-label', 'Diminuer');
        plus.setAttribute('aria-label', 'Augmenter');
        function step(delta) {
          var current = Number(input.value);
          var limits = core.TEMPERATURE_LIMITS.room;
          var next = Math.min(limits.max, Math.max(limits.min, Math.round((isNaN(current) ? limits.min : current) * 2) / 2 + delta));
          input.value = next;
          setRoomTemperature(zone, roomId, next);
        }
        minus.onclick = function () { step(-0.5); };
        plus.onclick = function () { step(0.5); };
        input.oninput = function () {
          setRoomTemperature(zone, roomId, input.value === '' ? NaN : Number(input.value));
        };
        row.appendChild(room);
        row.appendChild(minus);
        row.appendChild(input);
        row.appendChild(plus);
        var blockers = core.temperatureBlockers(home, schedule, zone, roomId);
        if (blockers.length) {
          input.disabled = minus.disabled = plus.disabled = true;
          row.title = 'Modification impossible : ' + blockers.join(', ');
          row.appendChild(element('span', 'blocked', 'non modifiable'));
        }
        box.appendChild(row);
      });
      container.appendChild(box);
    });
  }

  function updateDirtyState() {
    if (!state.editor || !currentSchedule()) {
      $('save').disabled = true;
      $('discard').disabled = true;
      return;
    }
    var dirty = isDirty();
    var errors = core.validationErrors(currentHome(), currentSchedule(), state.editor.baseline, state.editor.edited);
    var list = $('errors');
    clear(list);
    errors.forEach(function (message) { list.appendChild(element('li', null, message)); });
    list.hidden = !errors.length;
    var online = state.conn && state.conn.connected();
    $('save').disabled = !dirty || state.saving || errors.length > 0 || state.missing || !online;
    $('discard').disabled = !dirty || state.saving;
    $('refresh').disabled = state.saving;
    $('home').disabled = $('schedule').disabled = state.saving;
    $('away').disabled = $('hg').disabled = state.saving;
    $('save').textContent = state.saving ? 'Enregistrement…' : 'Enregistrer';
    $('dirty-state').textContent = dirty ? 'Modifications non enregistrées' : 'Aucune modification';
  }

  function showResults(outcome) {
    var okCount = outcome.results.filter(function (r) { return r.ok; }).length;
    var total = outcome.results.length;
    var title;
    if (outcome.complete) {
      title = 'Tout est enregistré.';
    } else if (okCount) {
      title = 'Enregistrement partiel : ' + okCount + ' sur ' + total
        + '. Les éléments en échec restent marqués comme non enregistrés.';
    } else {
      title = 'Échec de l\'enregistrement. Rien n\'a été modifié.';
    }
    $('results-title').textContent = title;
    var list = $('results-list');
    clear(list);
    outcome.results.forEach(function (result) {
      list.appendChild(element('li', result.ok ? 'ok' : 'failed',
        result.label + (result.ok ? '' : ' — ' + result.error)));
    });
    $('results').hidden = false;
    toast(title);
  }

  function hideResults() {
    $('results').hidden = true;
  }

  /* ---------- Slot dialog ---------- */

  var slotContext = null;

  function fillDays(select) {
    clear(select);
    DAYS_FULL.forEach(function (name, index) {
      var option = element('option', null, name);
      option.value = String(index);
      select.appendChild(option);
    });
  }

  function openSlotDialog(day, segment) {
    var model = state.editor.edited;
    fillDays($('slot-start-day'));
    fillDays($('slot-end-day'));
    var zoneSelect = $('slot-zone');
    clear(zoneSelect);
    model.zones.forEach(function (zone) {
      var option = element('option', null, zone.name);
      option.value = String(zone.id);
      zoneSelect.appendChild(option);
    });
    $('slot-start-day').value = $('slot-end-day').value = String(day);
    if (segment) {
      $('slot-title').textContent = 'Modifier le créneau';
      $('slot-start').value = core.formatClock(segment.start);
      $('slot-end').value = core.formatClock(segment.end % core.MINUTES_PER_DAY);
      zoneSelect.value = String(segment.zoneId);
    } else {
      $('slot-title').textContent = 'Ajouter un créneau';
      $('slot-start').value = '08:00';
      $('slot-end').value = '22:00';
      zoneSelect.value = String(model.zones[0].id);
    }
    $('slot-error').hidden = true;
    slotContext = { entityId: state.entityId };
    $('slot-dialog').showModal();
  }

  function applySlot(event) {
    event.preventDefault();
    if (!slotContext || slotContext.entityId !== state.entityId || !state.editor) {
      $('slot-dialog').close();
      return;
    }
    try {
      var bounds = core.slotOffsets($('slot-start-day').value, $('slot-start').value,
        $('slot-end-day').value, $('slot-end').value);
      state.editor.edited.timetable = core.replaceInterval(state.editor.edited.timetable,
        bounds[0], bounds[1], Number($('slot-zone').value));
    } catch (error) {
      $('slot-error').textContent = error.message;
      $('slot-error').hidden = false;
      return;
    }
    $('slot-dialog').close();
    hideResults();
    renderWeek();
    updateDirtyState();
  }

  /* ---------- Actions ---------- */

  function confirmDiscard() {
    return !isDirty() || window.confirm(UNSAVED_PROMPT);
  }

  function selectSchedule(homeId, entityId) {
    state.homeId = homeId;
    state.entityId = entityId;
    state.missing = false;
    chooseSelection();
    var schedule = currentSchedule();
    state.editor = schedule ? newEditor(schedule.model) : null;
    hideResults();
    render();
  }

  function reloadFromRemote() {
    var schedule = currentSchedule();
    state.missing = false;
    if (!schedule) {
      state.editor = null;
      chooseSelection();
      schedule = currentSchedule();
    }
    state.editor = schedule ? newEditor(schedule.model) : null;
    hideResults();
    render();
  }

  function save() {
    var home = currentHome();
    var schedule = currentSchedule();
    if (!home || !schedule || !isDirty() || state.saving) {
      return;
    }
    var editor = state.editor;
    state.saving = true;
    hideResults();
    render();
    var target = {
      homeId: home.id,
      scheduleId: schedule.id,
      rooms: home.rooms
    };
    core.saveSchedule(target, editor.baseline, editor.edited, function (service, data) {
      return state.conn.callService(service, data);
    }).then(function (outcome) {
      editor.pending = {
        stale: editor.baseline,
        model: core.cloneModel(outcome.confirmed),
        until: Date.now() + CONFIRMATION_WAIT_MS
      };
      editor.baseline = outcome.confirmed;
      editor.remoteChanged = false;
      state.saving = false;
      render();
      showResults(outcome);
      if (state.conn.mode === 'rest') {
        // Without a websocket, re-read soon so the confirmed state is followed.
        FOLLOW_UP_POLLS_MS.forEach(function (ms) { setTimeout(poll, ms); });
      }
    });
  }

  function refresh() {
    if (!confirmDiscard()) {
      return;
    }
    var connection = state.conn;
    state.saving = true;
    updateDirtyState();
    connection.callService('refresh_schedules', { home_id: state.homeId }).then(function () {
      // The iframe's state object follows the websocket shortly after the call.
      return delay(connection.mode === 'iframe' ? 1000 : 0);
    }).then(function () {
      return connection.getStates();
    }).then(function (states) {
      state.saving = false;
      state.signature = null;
      state.editor = null;
      applyStates(states);
      hideResults();
      toast('Plannings relus depuis le cloud.');
    }, function (error) {
      state.saving = false;
      updateDirtyState();
      toast('Rafraîchissement impossible : ' + core.errorMessage(error));
    });
  }

  function temperatureInput(field) {
    return function (event) {
      var raw = event.target.value;
      state.editor.edited[field] = raw === '' ? NaN : Number(raw);
      hideResults();
      updateDirtyState();
    };
  }

  function bind() {
    $('home').onchange = function () {
      var target = $('home').value;
      if (!confirmDiscard()) {
        $('home').value = state.homeId;
        return;
      }
      state.entityId = null;
      selectSchedule(target, null);
    };
    $('schedule').onchange = function () {
      var target = $('schedule').value;
      if (!confirmDiscard()) {
        $('schedule').value = state.entityId;
        return;
      }
      selectSchedule(state.homeId, target);
    };
    $('away').oninput = temperatureInput('awayTemp');
    $('hg').oninput = temperatureInput('hgTemp');
    $('save').onclick = save;
    $('discard').onclick = function () {
      state.editor.edited = core.cloneModel(state.editor.baseline);
      hideResults();
      render();
    };
    $('refresh').onclick = refresh;
    $('banner-reload').onclick = function () {
      if (confirmDiscard()) {
        reloadFromRemote();
      }
    };
    $('logout').onclick = function () {
      if (!confirmDiscard()) {
        return;
      }
      forgetToken();
      state.editor = null;
      state.homes = [];
      showSetup();
    };
    $('failure-standalone').onclick = function () { showSetup(); };
    $('setup-form').onsubmit = function (event) {
      event.preventDefault();
      var baseUrl;
      try {
        baseUrl = core.normalizeBaseUrl($('setup-url').value);
      } catch (error) {
        $('setup-error').textContent = error.message;
        $('setup-error').hidden = false;
        return;
      }
      var token = $('setup-token').value.trim();
      if (!token) {
        $('setup-error').textContent = 'Le token est requis.';
        $('setup-error').hidden = false;
        return;
      }
      $('setup-token').value = '';
      connectRest(baseUrl, token, $('setup-remember').checked);
    };
    $('slot-form').onsubmit = applySlot;
    $('slot-cancel').onclick = function () { $('slot-dialog').close(); };
    window.addEventListener('beforeunload', function (event) {
      if (isDirty()) {
        event.preventDefault();
        event.returnValue = '';
      }
    });
  }

  bind();
  start();
})();
