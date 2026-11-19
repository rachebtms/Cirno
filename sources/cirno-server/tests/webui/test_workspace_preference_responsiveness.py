"""Slow preference files must not block connection handling or escape cancellation."""

import asyncio
import inspect
import threading
from types import SimpleNamespace

import pytest
from cirno_server.webui import workspaces
from cirno_server.webui.http import files


@pytest.mark.parametrize("operation", ["stage", "persist", "favorite", "resolve"])
async def test_preference_io_settles_outside_the_event_loop(tmp_path, monkeypatch, operation):
    monkeypatch.setattr(workspaces, "get_webui_dir", lambda: tmp_path / "webui")
    entered, finished, release = (threading.Event() for _ in range(3))

    def slow(*args, **kwargs):
        entered.set()
        try:
            release.wait(1)
            project = {"path": str(tmp_path), "name": "project"}
            return [project] if operation == "favorite" else project
        finally:
            finished.set()

    if operation in {"stage", "persist"}:
        controller = workspaces.WebUIWorkspaceController(
            session_manager=None, default_workspace=tmp_path, default_restrict_to_workspace=True,
        )
        scope = controller.default_scope()
        monkeypatch.setattr(workspaces, "remember_webui_project", slow)
        def invoke():
            return getattr(controller, f"{operation}_scope")("slow-preferences", scope)
    else:
        server = SimpleNamespace(
            check_api_token=lambda request: True,
            workspace_project_selection_available=lambda connection: True,
            workspaces=SimpleNamespace(set_favorite_project=slow, resolve_project=slow),
        )
        monkeypatch.setattr(files, "_mutation_payload", lambda request: {"path": str(tmp_path), "pinned": True})
        routes = files.FilesRoutes(server)
        name = "_handle_workspace_favorite" if operation == "favorite" else "_handle_workspace_resolve_project"
        def invoke():
            return getattr(routes, name)(None, None)

    async def request():
        result = invoke()
        return await result if inspect.isawaitable(result) else result

    task = asyncio.create_task(request())
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        assert not finished.is_set(), "Preference I/O blocked the server event loop"
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Cancellation released an unfinished preference write"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
