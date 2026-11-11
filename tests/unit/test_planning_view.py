"""Bundled planning editor route: distribution, cache, lifecycle and auth boundary.

Requests go over a real aiohttp server on a Unix socket (TCP stays disabled)
through Home Assistant's own view registration and request wrapper.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
from aiohttp import web

from custom_components.intuis_connect import CONFIG_SCHEMA, async_setup, async_unload_entry
from custom_components.intuis_connect.planning_view import (
    PLANNING_ASSETS,
    PLANNING_DIRECTORY,
    PLANNING_URL,
    IntuisPlanningView,
)
from custom_components.intuis_connect.utils.const import DOMAIN

COMPONENT = Path(__file__).parents[2] / "custom_components" / DOMAIN
SECRET_VALUES = ("home-secret-id", "Chambre secrète", "refresh-secret", "access-secret")


def load_home(hass, entry_factory, home_id="home-secret-id"):
    entry = entry_factory(home_id=home_id, data={"refresh_token": "refresh-secret"})
    home = SimpleNamespace(
        id=home_id, name="Maison", schedules=[],
        rooms={"room": SimpleNamespace(name="Chambre secrète")},
    )
    api = SimpleNamespace(access_token="access-secret")
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"intuis_home": home, "api": api}
    return entry


@pytest.fixture
async def planning_client(ha_hass):
    """Start the view on a short Unix socket path; yield a request helper."""
    socket_dir = tempfile.mkdtemp(prefix="ic-")
    runners, sessions = [], []

    async def start(directory=PLANNING_DIRECTORY):
        app = web.Application()
        view = IntuisPlanningView(ha_hass, directory)
        view.register(ha_hass, app, app.router)
        runner = web.AppRunner(app)
        await runner.setup()
        path = f"{socket_dir}/{len(runners)}.sock"
        await web.UnixSite(runner, path).start()
        session = aiohttp.ClientSession(connector=aiohttp.UnixConnector(path=path))
        runners.append(runner)
        sessions.append(session)

        async def request(path="", method="GET", **kwargs):
            async with session.request(method, f"http://ha{PLANNING_URL}{path}", **kwargs) as response:
                return response.status, response.headers, await response.read()

        return request

    yield start
    for session in sessions:
        await session.close()
    for runner in runners:
        await runner.cleanup()
    shutil.rmtree(socket_dir, ignore_errors=True)


async def test_shell_is_public_static_and_holds_no_home_data(
    ha_hass, ha_entry_factory, planning_client
):
    load_home(ha_hass, ha_entry_factory)
    request = await planning_client()
    status, headers, body = await request()
    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert headers["Cache-Control"] == "no-cache"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'self'" in headers["Content-Security-Policy"]
    assert "script-src 'self';" in headers["Content-Security-Policy"]
    assert "Access-Control-Allow-Origin" not in headers
    page = body.decode()
    assert '<script src="planning/planning-core.js"' in page
    assert "<script>" not in page  # no inline script for the CSP to allow
    for asset in [name for name in PLANNING_ASSETS if name]:
        status, headers, served = await request(f"/{asset}")
        assert status == 200
        assert served == (PLANNING_DIRECTORY / asset).read_bytes()
        assert headers["Content-Type"].split(";")[0] == PLANNING_ASSETS[asset][1]
        page += served.decode()
    for secret in SECRET_VALUES:
        assert secret not in page


async def test_shell_credits_thefab21_sources(ha_hass, ha_entry_factory, planning_client):
    load_home(ha_hass, ha_entry_factory)
    request = await planning_client()
    page = (await request())[2].decode()
    assert "https://github.com/TheFab21" in page
    for pr in (17, 22, 24):
        assert f"https://github.com/antoine-pyre/intuis-connect/pull/{pr}" in page


@pytest.mark.parametrize(
    "path", ["/", "/index.html", "/..%2F__init__.py", "/%2e%2e/manifest.json", "/planning-core.js.map"]
)
async def test_only_published_assets_are_served(ha_hass, ha_entry_factory, planning_client, path):
    load_home(ha_hass, ha_entry_factory)
    request = await planning_client()
    assert (await request(path))[0] == 404


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
async def test_route_accepts_no_command(ha_hass, ha_entry_factory, planning_client, method):
    load_home(ha_hass, ha_entry_factory)
    request = await planning_client()
    assert (await request(method=method, json={"service": "sync_schedule"}))[0] == 405


async def test_matching_etag_revalidates_with_304(ha_hass, ha_entry_factory, planning_client):
    load_home(ha_hass, ha_entry_factory)
    request = await planning_client()
    _, headers, _ = await request("/planning-app.js")
    etag = headers["ETag"]
    for header in (etag, f"W/{etag}", f'"other", {etag}', "*"):
        status, revalidated, body = await request(
            "/planning-app.js", headers={"If-None-Match": header}
        )
        assert (status, body, revalidated["ETag"]) == (304, b"", etag)
        assert revalidated["Cache-Control"] == "no-cache"
    assert (await request("/planning-app.js", headers={"If-None-Match": '"other"'}))[0] == 200
    shell_etag = (await request())[1]["ETag"]
    assert shell_etag != etag


async def test_new_version_is_served_with_new_etag_and_missing_file_is_404(
    ha_hass, ha_entry_factory, planning_client, tmp_path
):
    """An integration update replaces files on disk; the next load revalidates."""
    load_home(ha_hass, ha_entry_factory)
    directory = tmp_path / "planning"
    shutil.copytree(PLANNING_DIRECTORY, directory)
    request = await planning_client(directory)
    _, headers, _ = await request()
    old_etag = headers["ETag"]
    updated = (directory / "index.html").read_text() + "<!-- next release -->\n"
    (directory / "index.html").write_text(updated)
    status, headers, body = await request(headers={"If-None-Match": old_etag})
    assert status == 200
    assert headers["ETag"] != old_etag
    assert body.decode() == updated
    assert "TheFab21" in body.decode()
    (directory / "planning.css").unlink()
    assert (await request("/planning.css"))[0] == 404


async def test_files_are_read_outside_the_event_loop(
    ha_hass, ha_entry_factory, planning_client, monkeypatch
):
    load_home(ha_hass, ha_entry_factory)
    request = await planning_client()
    readers = []
    original = Path.read_bytes

    def tracked(path):
        readers.append(threading.current_thread() is threading.main_thread())
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", tracked)
    assert (await request())[0] == 200
    assert readers == [False]
    assert (await request())[0] == 200
    assert readers == [False]  # unchanged file: served from the cached copy


async def test_route_follows_loaded_homes_through_unload_and_readd(
    ha_hass, ha_entry_factory, planning_client, monkeypatch
):
    monkeypatch.setattr(
        ha_hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
    )
    request = await planning_client()
    assert (await request())[0] == 404
    first = load_home(ha_hass, ha_entry_factory, "first")
    second = load_home(ha_hass, ha_entry_factory, "second")
    assert (await request())[0] == 200
    assert await async_unload_entry(ha_hass, first)
    assert (await request())[0] == 200
    assert await async_unload_entry(ha_hass, second)
    # Routes cannot be removed from a running HTTP server: it answers 404 instead.
    assert (await request())[0] == 404
    assert (await request("/planning-app.js"))[0] == 404
    load_home(ha_hass, ha_entry_factory, "second")
    assert (await request())[0] == 200


async def test_view_is_registered_once_per_run(ha_hass):
    http = ha_hass.http = Mock()
    try:
        assert await async_setup(ha_hass, {})
        assert await async_setup(ha_hass, {})
    finally:
        ha_hass.http = None
    http.register_view.assert_called_once()
    (view,), _ = http.register_view.call_args
    assert isinstance(view, IntuisPlanningView)
    assert view.url == PLANNING_URL and view.requires_auth is False
    assert view.cors_allowed is False


def test_manifest_declares_http_and_yaml_stays_config_entry_only():
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["dependencies"] == ["http"]
    assert CONFIG_SCHEMA({}) == {}
