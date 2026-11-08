"""Preferences use authenticated commands and report save conflicts to the browser."""

import json
from types import SimpleNamespace

import pytest
from cirno_core.profile.preferences import PreferencesRepository
from cirno_server.webui.http.preferences import preferences_response
from cirno_server.webui.http.shared import (
    _WEBUI_MUTATION_PAYLOAD_ATTR,
    _WEBUI_MUTATION_REQUEST_ATTR,
)
from websockets.datastructures import Headers
from websockets.http11 import Request


def request(payload, *, authenticated=True):
    value = Request("/v0/preferences", Headers())
    setattr(value, _WEBUI_MUTATION_REQUEST_ATTR, authenticated)
    setattr(value, _WEBUI_MUTATION_PAYLOAD_ATTR, payload)
    return value


@pytest.mark.asyncio
async def test_preferences_command_persists_and_rejects_stale_theme_edits(tmp_path):
    server = SimpleNamespace(preferences=PreferencesRepository(tmp_path / "preferences.sqlite3"))
    saved = await preferences_response(server, request({"patch": {"themeMode": "dark"}}))
    assert saved.status_code == 200
    assert json.loads(saved.body)["values"]["themeMode"] == "dark"
    read = await preferences_response(server, request({"operation": "read"}))
    assert read.body == saved.body
    rejected = await preferences_response(
        server, request({"patch": {"themeMode": "light"}, "expected_revision": 0})
    )
    assert rejected.status_code == 409
    assert server.preferences.read()["values"]["themeMode"] == "dark"


@pytest.mark.asyncio
async def test_preferences_rejects_unauthenticated_and_invalid_writes(tmp_path):
    server = SimpleNamespace(preferences=PreferencesRepository(tmp_path / "preferences.sqlite3"))
    denied = await preferences_response(
        server, request({"patch": {"themeMode": "dark"}}, authenticated=False)
    )
    assert denied.status_code == 405
    invalid = await preferences_response(server, request({"patch": {"themeMode": "invalid"}}))
    assert invalid.status_code == 400
    assert server.preferences.read()["revision"] == 0
