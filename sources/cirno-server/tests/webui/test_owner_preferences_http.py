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


@pytest.mark.parametrize("payload", [
    {"patch": None}, {"patch": []}, {"patch": "invalid"},
    {"patch": {"codeWrap": False}, "expected_revision": False},
    {"patch": {"codeWrap": False}, "expected_revision": 0.0},
    {"patch": {"codeWrap": False}, "expected_revision": -1},
    {"patch": {"codeWrap": False}, "operation": "unknown"},
])
async def test_invalid_preference_envelopes_return_400_without_writing(tmp_path, payload):
    store = PreferencesRepository(tmp_path / "preferences.sqlite3")
    before = store.read()
    response = await preferences_response(SimpleNamespace(preferences=store), request(payload))
    assert response.status_code == 400
    assert store.read() == before


@pytest.mark.parametrize("operation", [None, "update"])
async def test_preference_read_command_cannot_write_or_increment_revision(tmp_path, operation):
    from cirno_core.bus.queue import MessageBus
    from cirno_server.webui.http.handler import ServerHTTPHandler

    handler = ServerHTTPHandler.__new__(ServerHTTPHandler)
    handler.config = SimpleNamespace(token_issue_path=None)
    handler.bus = MessageBus()
    handler.preferences = PreferencesRepository(tmp_path / "preferences.sqlite3")
    before = handler.preferences.read()
    payload = {"patch": {"codeWrap": False}}
    if operation is not None:
        payload["operation"] = operation
    response = await handler.dispatch_webui_mutation(SimpleNamespace(), "preferences.read", payload)
    assert response.status_code == (200 if operation is None else 400)
    if operation is None:
        assert json.loads(response.body) == before
    assert handler.preferences.read() == before


async def test_preference_update_command_cannot_be_changed_into_a_read(tmp_path):
    from cirno_core.bus.queue import MessageBus
    from cirno_server.webui.http.handler import ServerHTTPHandler

    handler = ServerHTTPHandler.__new__(ServerHTTPHandler)
    handler.config = SimpleNamespace(token_issue_path=None)
    handler.bus = MessageBus()
    handler.preferences = PreferencesRepository(tmp_path / "preferences.sqlite3")
    response = await handler.dispatch_webui_mutation(
        SimpleNamespace(), "preferences.update", {"operation": "read", "patch": {"codeWrap": False}},
    )
    assert response.status_code == 400
    assert handler.preferences.read()["revision"] == 0


async def test_cancelled_preference_write_waits_for_the_accepted_database_write(tmp_path):
    import asyncio
    from threading import Event

    started, release, finished = Event(), Event(), Event()

    class GatedPreferences(PreferencesRepository):
        def update(self, patch, expected_revision=None):
            started.set()
            try:
                if not release.wait(2):
                    raise TimeoutError("Fixture write was not released")
                return super().update(patch, expected_revision)
            finally:
                finished.set()

    store = GatedPreferences(tmp_path / "preferences.sqlite3")
    task = asyncio.create_task(preferences_response(
        SimpleNamespace(preferences=store), request({"patch": {"codeWrap": False}}),
    ))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "The settings write escaped the operation's cancellation ownership"
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 2)
    assert task.cancelled()
    assert store.read()["values"]["codeWrap"] is False
