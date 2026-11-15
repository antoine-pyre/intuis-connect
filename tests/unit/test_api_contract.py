"""Transport regressions found while comparing the client with the Android APK.

These tests check local request handling, not cloud acceptance of legacy routes.
See docs/13-apk-api-audit.md for the evidence and remaining differences.
"""
from __future__ import annotations

import aiohttp
import pytest
from aioresponses import CallbackResult
from yarl import URL

from custom_components.intuis_connect.intuis_api.api import APIError, IntuisAPI
from custom_components.intuis_connect.utils.const import (
    APP_VERSION, AUTH_PATH, BASE_URLS, CLIENT_ID,
)


@pytest.mark.parametrize("base_url", BASE_URLS)
@pytest.mark.parametrize("operation", ["get", "set", "delete", "switch"])
async def test_schedule_requests_use_authenticated_cluster(cloud_responses, base_url, operation):
    """A fallback login must not send schedule operations to the primary cluster."""
    paths = {
        "get": ("get", "/api/gethomeschedule", {"home_id": "home", "schedule_id": "schedule"}),
        "set": ("post", "/api/updatenewhomeschedule", None),
        "delete": ("delete", "/api/deletenewhomeschedule", {"home_id": "home", "slot_id": "slot"}),
        "switch": ("post", "/api/switchhomeschedule", None),
    }
    method, path, params = paths[operation]
    seen = []

    def endpoint(url, **kwargs):
        seen.append(kwargs)
        return CallbackResult(payload={"rooms": [{"room_id": "room", "slots": []}]})

    url = URL(base_url + path).with_query(params or {})
    getattr(cloud_responses, method)(url, callback=endpoint)
    async with aiohttp.ClientSession() as session:
        api = IntuisAPI(session, home_id="home", min_request_delay=0)
        api._base_url = base_url
        api._access_token = "cluster-access"
        if operation == "get":
            assert await api.async_get_schedule("home", "schedule") == {"room": []}
        elif operation == "set":
            await api.async_set_schedule_slot("home", "schedule", "room", "08:00", "09:00", 20)
        elif operation == "delete":
            await api.async_delete_schedule_slot("home", "slot")
        else:
            await api.async_switch_schedule("home", "schedule")
    assert len(seen) == 1
    assert seen[0]["headers"]["Authorization"] == "Bearer cluster-access"
    if operation == "switch":
        assert seen[0]["json"] == {"home_id": "home", "schedule_id": "schedule"}


async def test_refresh_includes_app_version_and_keeps_client_identity(cloud_responses):
    """APK oh8.a sends app_version on refresh as well as on password login."""
    seen = []

    def endpoint(url, **kwargs):
        seen.append(kwargs["data"])
        return CallbackResult(payload={"access_token": "renewed", "refresh_token": "rotated"})

    cloud_responses.post(BASE_URLS[1] + AUTH_PATH, callback=endpoint)
    async with aiohttp.ClientSession() as session:
        api = IntuisAPI(session)
        api._base_url = BASE_URLS[1]
        api.refresh_token = "existing-refresh"
        await api.async_refresh_access_token()
        assert api.refresh_token == "rotated"
        assert api._access_token == "renewed"
    assert seen[0]["app_version"] == APP_VERSION
    assert seen[0]["grant_type"] == "refresh_token"
    assert seen[0]["refresh_token"] == "existing-refresh"
    assert seen[0]["client_id"] == CLIENT_ID


@pytest.mark.parametrize("operation,path", [
    ("setstate", "/syncapi/v1/setstate"),
    ("switchhomeschedule", "/api/switchhomeschedule"),
])
@pytest.mark.parametrize("refused", [True, False])
async def test_commands_check_application_errors(cloud_responses, operation, path, refused):
    """An HTTP 200 envelope may still report a rejected heating command."""
    response = {"error": {"code": 21, "message": "refused"}} if refused else {"status": "ok"}
    cloud_responses.post(BASE_URLS[0] + path, payload=response)
    async with aiohttp.ClientSession() as session:
        api = IntuisAPI(session, home_id="home", min_request_delay=0)
        api._access_token = "access"
        command = (
            api.async_set_room_state("room", "home") if operation == "setstate"
            else api.async_switch_schedule("home", "schedule")
        )
        if refused:
            with pytest.raises(APIError, match=f"{operation} failed:.*refused"):
                await command
        else:
            await command
