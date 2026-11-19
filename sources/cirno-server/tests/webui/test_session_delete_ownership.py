"""An accepted cascade delete retains ownership across caller cancellation."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.cron.types import CronJob
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.triggers.local_types import LocalTrigger
from cirno_server.webui.http.sessions import SessionsRoutes


@pytest.mark.parametrize("phase", ["automation", "discard", "database"])
async def test_cancellation_drains_the_whole_accepted_session_delete(monkeypatch, phase):
    loop = asyncio.get_running_loop()
    entered, release = asyncio.Event(), asyncio.Event()
    disk_release = threading.Event()
    completed = []
    jobs = [CronJob(id="cron", name="cron"), LocalTrigger(
        id="trigger", name="trigger", enabled=True, channel="websocket", chat_id="owner", session_key="websocket:owner",
    )]

    def delete_trigger(identifier):
        if phase == "automation":
            loop.call_soon_threadsafe(entered.set)
            if not disk_release.wait(1):
                raise RuntimeError("Fixture trigger deletion was not released")
        completed.append(identifier)

    async def discard(key):
        if phase == "discard":
            entered.set()
            await release.wait()
        completed.append("discard")

    async def delete_session(key):
        if phase == "database":
            entered.set()
            await release.wait()
        completed.append("database")
        return True

    server = SimpleNamespace(
        check_api_token=lambda _: True,
        session_manager=SimpleNamespace(state=SimpleNamespace(delete=AsyncMock(side_effect=delete_session))),
        cron_service=SimpleNamespace(remove_job=lambda identifier: completed.append(identifier)),
        local_trigger_store=SimpleNamespace(delete=delete_trigger),
        workspaces=SimpleNamespace(discard_draft_scope=Mock(return_value=False)),
        discard_session=discard, subagent_manager=None,
    )
    monkeypatch.setattr("cirno_server.webui.http.sessions.session_automation_jobs", lambda *args, **kwargs: jobs)
    route = SessionsRoutes(server)
    request = SimpleNamespace(path="/v0/sessions/websocket:owner/delete?delete_automations=1")
    task = asyncio.create_task(route._handle_session_delete(request, "websocket:owner"))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        disk_release.set()
        result, = await asyncio.gather(task, return_exceptions=True)
    assert isinstance(result, asyncio.CancelledError)
    assert completed == ["cron", "trigger", "discard", "database"]
    server.session_manager.state.delete.assert_awaited_once_with("websocket:owner")


@pytest.mark.parametrize("case,status", [("unauthorized", 401), ("router", 409), ("channel", 404), ("confirmation", 200)])
async def test_delete_preflight_rejections_do_not_start_cleanup(monkeypatch, case, status):
    server = SimpleNamespace(
        check_api_token=lambda _: case != "unauthorized",
        session_manager=SimpleNamespace(state=SimpleNamespace(delete=AsyncMock())),
        cron_service=SimpleNamespace(remove_job=Mock()), local_trigger_store=None,
        workspaces=SimpleNamespace(discard_draft_scope=Mock()), discard_session=AsyncMock(), subagent_manager=None,
    )
    jobs = [CronJob(id="cron", name="cron")] if case == "confirmation" else []
    monkeypatch.setattr("cirno_server.webui.http.sessions.session_automation_jobs", lambda *args, **kwargs: jobs)
    monkeypatch.setattr("cirno_server.webui.http.sessions.serialize_automation_jobs", lambda *args, **kwargs: [{"id": "cron"}])
    key = ROUTER_SESSION_KEY if case == "router" else "telegram:owner" if case == "channel" else "websocket:owner"
    response = await SessionsRoutes(server)._handle_session_delete(SimpleNamespace(path="/v0/sessions/delete"), key)
    assert response.status_code == status
    server.session_manager.state.delete.assert_not_awaited()
    server.discard_session.assert_not_awaited()
    server.workspaces.discard_draft_scope.assert_not_called()
    server.cron_service.remove_job.assert_not_called()


async def test_delete_operation_error_remains_an_error(monkeypatch):
    server = SimpleNamespace(
        check_api_token=lambda _: True,
        session_manager=SimpleNamespace(state=SimpleNamespace(delete=AsyncMock())),
        cron_service=None, local_trigger_store=None,
        workspaces=SimpleNamespace(discard_draft_scope=Mock(return_value=False)),
        discard_session=AsyncMock(side_effect=OSError("Fixture discard failed")), subagent_manager=None,
    )
    monkeypatch.setattr("cirno_server.webui.http.sessions.session_automation_jobs", lambda *args, **kwargs: [])
    with pytest.raises(OSError, match="Fixture discard failed"):
        await SessionsRoutes(server)._handle_session_delete(SimpleNamespace(path="/v0/sessions/delete"), "websocket:owner")
    server.session_manager.state.delete.assert_not_awaited()
