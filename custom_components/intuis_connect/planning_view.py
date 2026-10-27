"""Serve the bundled planning editor (adapted from TheFab21's #17/#22/#24).

The route only serves a static shell and its assets. They contain no home data,
token or command: the editor reads states and calls services through Home
Assistant's authenticated APIs (the parent ``hass`` object in an iframe, or a
user-supplied token in a standalone tab).
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from http import HTTPStatus
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .service_targets import target_entries
from .utils.const import DOMAIN

PLANNING_URL = "/api/intuis_connect/planning"
PLANNING_DIRECTORY = Path(__file__).parent / "resources" / "planning"
# Published name -> (file, content type). Anything else is a 404, never a path.
PLANNING_ASSETS = {
    "": ("index.html", "text/html"),
    "planning.css": ("planning.css", "text/css"),
    "planning-core.js": ("planning-core.js", "text/javascript"),
    "planning-app.js": ("planning-app.js", "text/javascript"),
}
PLANNING_HEADERS = {
    # Revalidate every load so an integration update is picked up immediately.
    "Cache-Control": "no-cache",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self' http: https:; "
        "frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}
_VIEW_REGISTERED = f"{DOMAIN}_planning_view"


@dataclass(frozen=True)
class _Asset:
    body: bytes
    etag: str
    version: tuple[int, int]


def _etag_matches(header: str | None, etag: str) -> bool:
    """Weak comparison of an If-None-Match list, as RFC 9110 requires for GET."""
    if not header:
        return False
    candidates = {
        value.strip().removeprefix("W/") for value in header.split(",")
    }
    return "*" in candidates or etag in candidates


class IntuisPlanningView(HomeAssistantView):
    """Static planning shell, available while at least one home is loaded."""

    url = PLANNING_URL
    extra_urls = [f"{PLANNING_URL}/{{asset}}"]
    name = "api:intuis_connect:planning"
    # A dashboard iframe cannot send a bearer token; the shell holds no data.
    requires_auth = False

    def __init__(self, hass: HomeAssistant, directory: Path = PLANNING_DIRECTORY) -> None:
        self._hass = hass
        self._directory = directory
        self._cache: dict[str, _Asset] = {}

    def _load(self, filename: str) -> _Asset | None:
        """Executor job: re-read a file only when its size or mtime changed."""
        path = self._directory / filename
        try:
            stat = path.stat()
            version = (stat.st_mtime_ns, stat.st_size)
            cached = self._cache.get(filename)
            if cached is not None and cached.version == version:
                return cached
            body = path.read_bytes()
        except OSError:
            return None
        asset = _Asset(body, f'"{sha256(body).hexdigest()[:32]}"', version)
        self._cache[filename] = asset
        return asset

    async def get(self, request: web.Request, asset: str = "") -> web.Response:
        published = PLANNING_ASSETS.get(asset)
        if published is None or not target_entries(self._hass):
            raise web.HTTPNotFound()
        filename, content_type = published
        loaded = await self._hass.async_add_executor_job(self._load, filename)
        if loaded is None:
            raise web.HTTPNotFound()
        headers = {**PLANNING_HEADERS, "ETag": loaded.etag}
        if _etag_matches(request.headers.get("If-None-Match"), loaded.etag):
            return web.Response(status=HTTPStatus.NOT_MODIFIED, headers=headers)
        return web.Response(
            body=loaded.body,
            content_type=content_type,
            charset="utf-8",
            headers=headers,
        )


def async_register_planning_view(hass: HomeAssistant) -> None:
    """Register once per Home Assistant run; HTTP routes cannot be removed."""
    if hass.data.get(_VIEW_REGISTERED):
        return
    hass.http.register_view(IntuisPlanningView(hass))
    hass.data[_VIEW_REGISTERED] = True
