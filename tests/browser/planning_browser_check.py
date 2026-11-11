"""Drive the bundled planning editor in real Firefox and Chromium browsers.

Not collected by pytest. Run from the repository root with a test environment:

    python tests/browser/planning_browser_check.py [--browser chrome|firefox|all] [--long]
    python tests/browser/planning_browser_check.py --serve 8765   # manual checks

A local Home Assistant core object registers the integration's real services
and planning view; schedule summary attributes come from the real sensor
class. Only the Intuis cloud (accepting or refusing commands), the coordinator
publication delay and the dashboard frame around the editor are simulated.
Browsers run headless through their own remote protocols (Chrome DevTools
Protocol, Firefox WebDriver BiDi); nothing contacts Intuis or external hosts.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import voluptuous as vol
from aiohttp import web

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError  # noqa: E402

from custom_components.intuis_connect.entity.intuis_home_entity import (  # noqa: E402
    IntuisScheduleSummarySensor,
)
from custom_components.intuis_connect.entity.intuis_schedule import IntuisSchedule  # noqa: E402
from custom_components.intuis_connect.intuis_api.api import APIError  # noqa: E402
from custom_components.intuis_connect.planning_view import PLANNING_URL, IntuisPlanningView  # noqa: E402
from custom_components.intuis_connect.services import async_register_services  # noqa: E402
from custom_components.intuis_connect.utils.const import DOMAIN  # noqa: E402

TOKEN = "harness-token"
XSS_ZONE = '<img src=x onerror="window.__xss=1">Éco'
IFRAME_SANDBOX = (
    "allow-forms allow-popups allow-pointer-lock allow-same-origin "
    "allow-scripts allow-modals allow-downloads"
)  # Home Assistant frontend src/util/iframe.ts


def schedule(schedule_id, name, selected, zones):
    return IntuisSchedule.from_dict({
        "id": schedule_id, "name": name, "type": "therm", "selected": selected,
        "away_temp": 16, "hg_temp": 7,
        "timetable": [
            {"m_offset": 0, "zone_id": 1}, {"m_offset": 420, "zone_id": 2},
            {"m_offset": 1320, "zone_id": 1}, {"m_offset": 9060, "zone_id": len(zones)},
        ],
        "zones": zones,
    })


def zones(rooms, names=("Nuit", "Confort", XSS_ZONE)):
    return [
        {"id": index + 1, "name": name, "type": index,
         "rooms_temp": [{"room_id": room, "temp": 17 + index} for room in rooms]}
        for index, name in enumerate(names)
    ]


class FakeCloud:
    """Accepts synchomeschedule payloads, or refuses those touching chosen rooms."""

    def __init__(self, harness, home):
        self.harness, self.home = harness, home
        self._schedule_mutation_locks = {}

    async def async_sync_schedule(self, *, schedule_id, zones, **payload):
        await asyncio.sleep(0.2)
        current = next(s for s in self.home.schedules if s.id == schedule_id)
        before = {(z.id, rt.room_id): rt.temp for z in current.zones for rt in z.rooms_temp}
        for zone in zones:
            for room in zone["rooms_temp"]:
                if (room["room_id"] in self.harness.failing_rooms
                        and before.get((zone["id"], room["room_id"])) != room["temp"]):
                    raise APIError("Intuis refused the change")

    async def async_get_homes_data(self):
        return deepcopy(self.home)

    async def async_switch_schedule(self, home_id, schedule_id):
        return None


class Harness:
    def __init__(self, config_dir):
        self.hass = HomeAssistant(config_dir)
        self.failing_rooms: set[str] = set()
        self.down = False
        self.lag = 2.0
        self.states: dict[str, dict] = {}

    def build_homes(self):
        self.homes = {
            "home-1": SimpleNamespace(
                id="home-1", name="Maison",
                rooms={"r1": SimpleNamespace(name="Salon"), "r2": SimpleNamespace(name="Chambre"),
                       "r3": SimpleNamespace(name="Bureau")},
                schedules=[schedule("s-week", "Semaine", True, zones(["r1", "r2", "r3"])),
                           schedule("s-away", "Vacances", False, zones(["r1", "r2", "r3"]))],
            ),
            "home-2": SimpleNamespace(
                id="home-2", name="Chalet", rooms={"c1": SimpleNamespace(name="Séjour")},
                schedules=[schedule("s-chalet", "Hiver", True, zones(["c1"], ("Nuit", "Jour")))],
            ),
        }

    def reset(self):
        """Start every browser flow from the same cloud model."""
        self.build_homes()
        self.hass.data[DOMAIN] = {}
        for home in self.homes.values():
            coordinator = SimpleNamespace(async_request_refresh=self._refresh_later)
            self.hass.data[DOMAIN][f"entry-{home.id}"] = {
                "intuis_home": home, "api": FakeCloud(self, home), "coordinator": coordinator,
            }
        self.publish()

    async def setup(self):
        self.reset()
        await async_register_services(self.hass, None)

    async def _refresh_later(self):
        # Like a debounced coordinator refresh, states follow the model with a lag.
        self.hass.loop.call_later(self.lag, self.publish)

    def publish(self):
        states = {}
        for home in self.homes.values():
            for item in home.schedules:
                sensor = IntuisScheduleSummarySensor(
                    SimpleNamespace(data={"intuis_home": home}), home.id, item
                )
                entity_id = f"sensor.{home.id.replace('-', '_')}_schedule_{item.id.replace('-', '_')}"
                states[entity_id] = {
                    "entity_id": entity_id, "state": sensor.native_value,
                    "attributes": json.loads(json.dumps(sensor.extra_state_attributes)),
                    "last_updated": time.time(),
                }
        self.states = states

    def external_edit(self):
        target = self.homes["home-1"].schedules[0]
        target.hg_temp = 9.0
        self.publish()

    # ---------------- HTTP ----------------
    def authorized(self, request):
        return request.headers.get("Authorization") == f"Bearer {TOKEN}"

    async def api_states(self, request):
        if self.down:
            return web.Response(status=503, text="Starting")
        if not self.authorized(request):
            return web.Response(status=401, text="401: Unauthorized")
        states = list(self.states.values())
        if "foreign" in request.query:
            # Another platform's sensor with the same attributes; the dashboard
            # registry marks it foreign and the editor must ignore it.
            foreign = deepcopy(states[0])
            foreign["entity_id"], foreign["state"] = "sensor.foreign_schedule", "Étranger"
            states.append(foreign)
        return web.json_response(states)

    async def api_service(self, request):
        if self.down:
            return web.Response(status=503, text="Starting")
        if not self.authorized(request):
            return web.Response(status=401, text="401: Unauthorized")
        domain, service = request.match_info["domain"], request.match_info["service"]
        data = await request.json()
        try:
            await self.hass.services.async_call(domain, service, data, blocking=True)
        except vol.Invalid:
            return web.Response(status=400, text="400: Bad Request")
        except ServiceValidationError as err:  # same mapping as HA 2026's REST API
            return web.json_response({"message": str(err)}, status=400)
        except HomeAssistantError as err:
            return web.json_response({"message": str(err)}, status=500)
        except Exception:  # noqa: BLE001 - an unhandled handler error is a bare 500
            return web.Response(status=500, text="500 Internal Server Error")
        return web.json_response([])

    async def control(self, request):
        body = await request.json()
        if "fail_rooms" in body:
            self.failing_rooms = set(body["fail_rooms"])
        if "down" in body:
            self.down = body["down"]
        if "lag" in body:
            self.lag = body["lag"]
        if body.get("reset"):
            self.reset()
        if body.get("external_edit"):
            self.external_edit()
        return web.json_response({"ok": True})

    async def dashboard(self, request):
        return web.Response(text=DASHBOARD, content_type="text/html")

    def app(self):
        app = web.Application()
        view = IntuisPlanningView(self.hass)
        view.register(self.hass, app, app.router)
        app.router.add_get("/api/states", self.api_states)
        app.router.add_post("/api/services/{domain}/{service}", self.api_service)
        app.router.add_post("/harness/control", self.control)
        app.router.add_get("/dashboard", self.dashboard)
        return app


# A stand-in for HA's frontend: <home-assistant>.hass is replaced on every update.
DASHBOARD = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Dashboard</title></head>
<body><home-assistant></home-assistant><script>
const params = new URLSearchParams(location.search);
const host = document.querySelector('home-assistant');
const token = '%(token)s';
async function callService(domain, service, data) {
  const response = await fetch(`/api/services/${domain}/${service}`, {
    method: 'POST', headers: {Authorization: `Bearer ${token}`}, body: JSON.stringify(data)});
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try { message = (await response.json()).message || message; } catch (e) {}
    throw {code: 'home_assistant_error', message};
  }
  return {};
}
async function update() {
  const response = await fetch('/api/states?foreign=1', {headers: {Authorization: `Bearer ${token}`}});
  if (!response.ok) { if (host.hass) host.hass = {...host.hass, connected: false}; return; }
  const states = {};
  for (const state of await response.json()) states[state.entity_id] = state;
  const entities = {};
  for (const id of Object.keys(states)) entities[id] = {platform: id === 'sensor.foreign_schedule' ? 'other' : 'intuis_connect'};
  host.hass = {states, entities, connected: true, callService,
               themes: {darkMode: params.get('dark') === '1'}};
}
const start = params.get('delay') === 'never' ? null : Number(params.get('delay') || 0);
if (start !== null) setTimeout(() => { update(); setInterval(update, 500); }, start);
const frame = document.createElement('iframe');
frame.setAttribute('sandbox', '%(sandbox)s');
frame.style.width = '1100px'; frame.style.height = '900px';
frame.src = '/api/intuis_connect/planning';
document.body.appendChild(frame);
</script></body></html>""" % {"token": TOKEN, "sandbox": IFRAME_SANDBOX}


# ---------------- Browser drivers ----------------
PRELUDE = """
const w = %s; const doc = w.document;
const $ = (id) => doc.getElementById(id);
const visible = (id) => { const e = $(id); return !!e && !e.closest('[hidden]'); };
const text = (id) => ($(id) ? $(id).textContent : null);
const set = (el, value) => { el.value = value;
  el.dispatchEvent(new w.Event('input', {bubbles: true}));
  el.dispatchEvent(new w.Event('change', {bubbles: true})); };
"""


def wrap(body, frame):
    target = "document.querySelector('iframe').contentWindow" if frame else "window"
    return ("(async () => {" + PRELUDE % target
            + "return JSON.stringify(await (async () => {" + body + "})()); })()")


class ChromeDriver:
    name = "chromium"

    def __init__(self, workdir):
        self.workdir = workdir

    async def start(self, session):
        self.process = subprocess.Popen(
            ["google-chrome", "--headless=new", "--no-first-run", "--no-default-browser-check",
             "--remote-debugging-port=9333", f"--user-data-dir={self.workdir}/chrome", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                async with session.put("http://127.0.0.1:9333/json/new?about:blank") as response:
                    target = await response.json()
                    break
            except aiohttp.ClientError:
                await asyncio.sleep(0.2)
        self.ws = await session.ws_connect(target["webSocketDebuggerUrl"], max_msg_size=0)
        self.counter = 0

    async def send(self, method, params=None):
        self.counter += 1
        await self.ws.send_json({"id": self.counter, "method": method, "params": params or {}})
        while True:
            message = await self.ws.receive_json()
            if message.get("id") == self.counter:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message["result"]

    async def navigate(self, url):
        await self.send("Page.navigate", {"url": url})
        await asyncio.sleep(0.5)

    async def evaluate(self, expression):
        result = await self.send("Runtime.evaluate", {
            "expression": expression, "awaitPromise": True, "returnByValue": True})
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result["result"].get("value")

    async def close(self):
        await self.ws.close()
        self.process.terminate()
        self.process.wait(10)


class FirefoxDriver:
    name = "firefox"

    def __init__(self, workdir):
        # The snap package cannot read /tmp; keep its profile in its own area.
        self.profile = Path.home() / "snap/firefox/common/intuis-planning-check"
        if not Path("/snap/bin/firefox").exists():
            self.profile = Path(workdir) / "firefox"

    async def start(self, session):
        self.profile.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen(
            ["firefox", "--headless", "--no-remote", "--remote-debugging-port", "9334",
             "--profile", str(self.profile), "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                self.ws = await session.ws_connect("ws://127.0.0.1:9334/session", max_msg_size=0)
                break
            except aiohttp.ClientError:
                await asyncio.sleep(0.2)
        self.counter = 0
        await self.send("session.new", {"capabilities": {"alwaysMatch": {
            "unhandledPromptBehavior": {"default": "accept"}}}})
        tree = await self.send("browsingContext.getTree", {})
        self.context = tree["contexts"][0]["context"]

    async def send(self, method, params):
        self.counter += 1
        await self.ws.send_json({"id": self.counter, "method": method, "params": params})
        while True:
            message = await self.ws.receive_json()
            if message.get("id") == self.counter:
                if message.get("type") == "error":
                    raise RuntimeError(message)
                return message["result"]

    async def navigate(self, url):
        await self.send("browsingContext.navigate", {"context": self.context, "url": url, "wait": "complete"})

    async def evaluate(self, expression):
        result = await self.send("script.evaluate", {
            "expression": expression, "target": {"context": self.context}, "awaitPromise": True})
        if result.get("type") == "exception":
            raise RuntimeError(result["exceptionDetails"])
        return result["result"].get("value")

    async def close(self):
        try:
            await self.send("session.end", {})
        except Exception:  # noqa: BLE001 - the browser may already be closing
            pass
        await self.ws.close()
        self.process.terminate()
        self.process.wait(10)
        shutil.rmtree(self.profile, ignore_errors=True)


# ---------------- Scenarios ----------------
class Run:
    def __init__(self, driver, base, session):
        self.driver, self.base, self.session = driver, base, session
        self.results: list[tuple[str, bool, str]] = []
        self.frame = False

    async def js(self, body):
        value = await self.driver.evaluate(wrap(body, self.frame))
        return json.loads(value) if value is not None else None

    async def until(self, body, timeout=10.0):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                last = await self.js(body)
                if last:
                    return last
            except RuntimeError as err:
                last = str(err)
            await asyncio.sleep(0.2)
        raise AssertionError(f"timed out waiting for: {body} (last: {last})")

    async def control(self, **body):
        async with self.session.post(f"{self.base}/harness/control", json=body) as response:
            assert response.status == 200

    def check(self, label, condition, detail=""):
        self.results.append((label, bool(condition), detail))
        print(f"  [{'PASS' if condition else 'FAIL'}] {self.driver.name}: {label} {detail}")

    async def step(self, label, coroutine):
        try:
            await coroutine
        except Exception as err:  # noqa: BLE001 - report and continue with the next step
            self.check(label, False, repr(err)[:400])


async def editor_flow(run: Run, mode: str):
    """Rendering, slot edit, partial failure, retry and stale-state handling."""
    await run.until("return visible('editor') && $('week').querySelectorAll('.row').length === 7")
    run.check(f"{mode}: seven-day grid rendered", True)
    first = await run.js("return [...$('schedule').options].map(o => o.textContent)")
    run.check(f"{mode}: first home (by name) opened on its active schedule", first == ["Hiver (actif)"], str(first))
    await run.js("set($('home'), 'home-1'); return true")
    legend = await run.js("return text('legend')")
    xss = await run.js("return [w.__xss === undefined, doc.querySelectorAll('img').length]")
    run.check(f"{mode}: HTML zone name rendered literally", XSS_ZONE in legend and xss == [True, 0],
              f"{legend!r} {xss}")
    options = await run.js("return [...$('schedule').options].map(o => o.textContent)")
    run.check(f"{mode}: schedules of the selected home only",
              options == ["Semaine (actif)", "Vacances"] if mode == "iframe" else "Semaine (actif)" in options,
              str(options))
    homes = await run.js("return [visible('home-field'), [...$('home').options].map(o => o.value)]")
    run.check(f"{mode}: home selector lists both homes", homes == [True, ["home-2", "home-1"]], str(homes))

    # Slot edit through the dialog: Monday 22:00 → Tuesday 06:00 becomes Confort.
    await run.js("""$('week').querySelectorAll('.add')[0].click();
      set($('slot-start-day'), '0'); set($('slot-start'), '22:00');
      set($('slot-end-day'), '1'); set($('slot-end'), '06:00'); set($('slot-zone'), '2');
      $('slot-form').requestSubmit(); return true;""")
    dirty = await run.until("return !$('slot-dialog').open && text('dirty-state')")
    run.check(f"{mode}: slot edit marks unsaved changes", dirty == "Modifications non enregistrées", dirty)
    tuesday = await run.js("return [...$('week').querySelectorAll('.row')[1].querySelectorAll('.seg')].map(s => s.title)")
    run.check(f"{mode}: midnight-crossing slot shown on next day",
              tuesday and tuesday[0].startswith("Mardi 00:00–06:00 : Confort"), str(tuesday))
    invalid = await run.js("""$('week').querySelectorAll('.add')[0].click();
      set($('slot-start-day'), '0'); set($('slot-start'), '10:00');
      set($('slot-end-day'), '0'); set($('slot-end'), '09:00');
      $('slot-form').requestSubmit();
      const shown = [$('slot-dialog').open, text('slot-error')]; $('slot-cancel').click(); return shown;""")
    run.check(f"{mode}: invalid slot refused in the dialog", invalid[0] and "fin" in invalid[1], str(invalid))

    # Room temperatures: Salon succeeds, Chambre is refused by the cloud.
    await run.control(fail_rooms=["r2"], lag=2.0)
    await run.js("""const inputs = [...$('zones').querySelectorAll('input')];
      const room = (name) => inputs.find(i => i.getAttribute('aria-label').startsWith(name + ', Confort'));
      set(room('Salon'), '21.5'); set(room('Chambre'), '20.5'); return true;""")
    await run.js("$('save').click(); return true")
    title = await run.until("return !$('results').hidden && text('results-title')", 15)
    items = await run.js("return [...$('results-list').children].map(li => [li.className, li.textContent])")
    run.check(f"{mode}: partial save reported", title.startswith("Enregistrement partiel : 2 sur 3"),
              f"{title} {items}")
    run.check(f"{mode}: each step listed with its outcome",
              [c for c, _ in items] == ["ok", "ok", "failed"] and "Chambre" in items[2][1], str(items))
    still = await run.js("return [text('dirty-state'), $('save').disabled]")
    run.check(f"{mode}: refused change stays unsaved", still == ["Modifications non enregistrées", False], str(still))
    await asyncio.sleep(3)  # the delayed publication arrives while Chambre is still edited
    kept = await run.js("""const i = [...$('zones').querySelectorAll('input')]
      .find(i => i.getAttribute('aria-label') === 'Chambre, Confort'); return [i.value, text('dirty-state')]""")
    run.check(f"{mode}: remote update keeps the unsaved edit", kept == ["20.5", "Modifications non enregistrées"], str(kept))
    salon = await run.js("""return [...$('zones').querySelectorAll('input')]
      .find(i => i.getAttribute('aria-label') === 'Salon, Confort').value""")
    run.check(f"{mode}: confirmed change retained", salon == "21.5", salon)

    # Retry once the cloud accepts: everything saved, no revert while states lag.
    await run.control(fail_rooms=[], lag=3.0)
    await run.js("$('save').click(); return true")
    title = await run.until("return !$('results').hidden && !$('save').textContent.includes('…') && text('results-title')", 15)
    run.check(f"{mode}: retry completes", title == "Tout est enregistré.", title)
    await asyncio.sleep(1)
    early = await run.js("""return [text('dirty-state'), [...$('zones').querySelectorAll('input')]
      .find(i => i.getAttribute('aria-label') === 'Chambre, Confort').value]""")
    run.check(f"{mode}: stale state during publication lag is ignored",
              early == ["Aucune modification", "20.5"], str(early))
    await asyncio.sleep(3)
    late = await run.js("""return [text('dirty-state'), [...$('zones').querySelectorAll('input')]
      .find(i => i.getAttribute('aria-label') === 'Chambre, Confort').value, visible('banner')]""")
    run.check(f"{mode}: confirmed state then followed", late == ["Aucune modification", "20.5", False], str(late))

    # An edit made elsewhere while there are unsaved changes shows a banner.
    await run.js("set($('away'), '17'); return true")
    await run.control(external_edit=True)
    banner = await run.until("return visible('banner') && text('banner-text')", run.driver_poll + 5)
    run.check(f"{mode}: external change signalled without losing edits",
              "modifié en dehors" in banner and await run.js("return $('away').value") == "17", banner)
    await run.js("w.confirm = () => true; $('banner-reload').click(); return true")
    reloaded = await run.js("return [$('hg').value, $('away').value, visible('banner')]")
    run.check(f"{mode}: reload takes the external version", reloaded == ["9", "16", False], str(reloaded))

    # Away/frost limits follow the service ranges.
    await run.js("set($('hg'), '15.5'); return true")
    errors = await run.js("return [visible('errors'), text('errors'), $('save').disabled]")
    run.check(f"{mode}: out-of-range frost temperature blocks saving",
              errors[0] and "Hors-gel" in errors[1] and errors[2], str(errors))
    await run.js("$('discard').click(); return true")

    # Switching home with unsaved changes asks first.
    await run.js("set($('away'), '18'); w.confirm = () => false; set($('home'), 'home-2'); return true")
    refused = await run.js("return [$('home').value, $('away').value]")
    run.check(f"{mode}: unsaved changes guard home switch", refused == ["home-1", "18"], str(refused))
    await run.js("w.confirm = () => true; set($('home'), 'home-2'); return true")
    switched = await run.js("return [[...$('schedule').options].map(o => o.textContent), text('zones').includes('Séjour')]")
    run.check(f"{mode}: other home shows its own schedules", switched == [["Hiver (actif)"], True], str(switched))
    await run.js("set($('home'), 'home-1'); return true")


async def reset_harness(run):
    await run.control(fail_rooms=[], down=False, lag=2.0, reset=True)


async def standalone(run: Run):
    run.frame = False
    run.driver_poll = 30
    await reset_harness(run)
    await run.driver.navigate(f"{run.base}/api/intuis_connect/planning")
    url = await run.until("return visible('setup') && $('setup-url').value")
    run.check("standalone: setup form with this origin", url == run.base, url)
    await run.js("set($('setup-token'), 'wrong'); $('setup-form').requestSubmit(); return true")
    refused = await run.until("return visible('setup') && !$('setup-error').hidden && text('setup-error')")
    run.check("standalone: rejected token reported", "Token refusé" in refused, refused)
    await run.js(f"set($('setup-token'), '{TOKEN}'); $('setup-form').requestSubmit(); return true")
    await run.until("return visible('app')")
    stored = await run.js(f"""return [sessionStorage.getItem('intuis_planning_token') === '{TOKEN}',
      localStorage.getItem('intuis_planning_token'), location.href.includes('{TOKEN}'),
      doc.documentElement.outerHTML.includes('{TOKEN}')]""")
    run.check("standalone: token kept for the session only, never in URL/DOM",
              stored == [True, None, False, False], str(stored))
    await editor_flow(run, "standalone")

    # Reload in the same tab: session token reused; HA restarting is retried.
    await run.control(down=True)
    await run.driver.navigate(f"{run.base}/api/intuis_connect/planning")
    waiting = await run.until("return visible('loading') && text('loading-text').includes('nouvel essai')")
    run.check("standalone: restart retried with countdown", bool(waiting), str(waiting))
    await asyncio.sleep(3)
    await run.control(down=False)
    await run.until("return visible('app') && visible('editor')", 20)
    run.check("standalone: reconnected after restart", True)

    await run.js("w.confirm = () => true; $('logout').click(); return true")
    cleared = await run.js("""return [visible('setup'), sessionStorage.getItem('intuis_planning_token'),
      localStorage.getItem('intuis_planning_token')]""")
    run.check("standalone: logout clears the token", cleared == [True, None, None], str(cleared))

    await run.js(f"localStorage.setItem('intuis_ha_token_saved', 'legacy'); set($('setup-token'), '{TOKEN}'); $('setup-remember').checked = true; $('setup-form').requestSubmit(); return true")
    await run.until("return visible('app')")
    remembered = await run.js(f"return [localStorage.getItem('intuis_planning_token') === '{TOKEN}', sessionStorage.getItem('intuis_planning_token')]")
    run.check("standalone: remember stores the token locally only on request", remembered == [True, None], str(remembered))
    await run.js("w.confirm = () => true; $('logout').click(); return true")
    legacy = await run.js("return [localStorage.getItem('intuis_planning_token'), localStorage.getItem('intuis_ha_token_saved')]")
    run.check("standalone: logout also clears the previous copies' token", legacy == [None, None], str(legacy))


async def iframe(run: Run, long: bool):
    run.frame = True
    run.driver_poll = 2
    await reset_harness(run)
    await run.driver.navigate(f"{run.base}/dashboard?dark=1&delay=3000")
    countdown = await run.until("return visible('loading') && text('loading-text').includes('reconnexion')")
    run.check("iframe: waits for hass with a countdown", bool(countdown), str(countdown))
    await run.until("return visible('app')", 10)
    status = await run.js("""return [text('connection-status'), visible('logout'), doc.documentElement.dataset.theme,
      w.getComputedStyle(doc.body).backgroundColor]""")
    run.check("iframe: session used without token, HA dark theme followed",
              status == ["Session Home Assistant", False, "dark", "rgb(26, 26, 26)"], str(status))
    foreign = await run.js("return [...$('schedule').options].some(o => o.textContent.includes('Étranger'))")
    run.check("iframe: other platforms' sensors ignored", foreign is False)
    storage = await run.js("""return [sessionStorage.getItem('intuis_planning_token'),
      localStorage.getItem('intuis_planning_token')]""")
    run.check("iframe: no token stored", storage == [None, None], str(storage))
    await editor_flow(run, "iframe")
    if long:
        await run.driver.navigate(f"{run.base}/dashboard?delay=never")
        message = await run.until("return visible('failure') && text('failure-text')", 50)
        run.check("iframe: bounded 45 s wait ends with an error", "45 secondes" in message, message)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", choices=["chrome", "firefox", "all"], default="all")
    parser.add_argument("--long", action="store_true", help="include the 45 s timeout")
    parser.add_argument("--serve", type=int, metavar="PORT",
                        help="only serve the simulated Home Assistant for manual checks")
    options = parser.parse_args()
    workdir = tempfile.mkdtemp(prefix="intuis-planning-")
    harness = Harness(workdir)
    await harness.setup()
    runner = web.AppRunner(harness.app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", options.serve or 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    if options.serve:
        print(f"Dashboard: {base}/dashboard  Standalone: {base}{PLANNING_URL} (token {TOKEN})")
        await asyncio.Event().wait()
    drivers = {"chrome": [ChromeDriver], "firefox": [FirefoxDriver]}.get(
        options.browser, [ChromeDriver, FirefoxDriver])
    failures = 0
    async with aiohttp.ClientSession() as session:
        for driver_class in drivers:
            driver = driver_class(workdir)
            await driver.start(session)
            run = Run(driver, base, session)
            print(f"== {driver.name}")
            try:
                await run.step("standalone flow", standalone(run))
                await run.step("iframe flow", iframe(run, options.long))
            finally:
                await driver.close()
            failures += sum(not ok for _, ok, _ in run.results)
            print(f"== {driver.name}: {sum(ok for _, ok, _ in run.results)}/{len(run.results)} passed")
    await runner.cleanup()
    await harness.hass.async_stop(force=True)
    shutil.rmtree(workdir, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
