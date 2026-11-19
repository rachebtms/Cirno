"""Workspace preference changes merge against the same owned file snapshot."""

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest
from cirno_core.utils.file_transactions import file_write_transaction
from cirno_server.webui import workspaces


@pytest.mark.parametrize("second_change", ["mode", "favorite"])
def test_recent_project_cannot_overwrite_a_concurrent_setting(tmp_path, monkeypatch, second_change):
    monkeypatch.setattr(workspaces, "get_webui_dir", lambda: tmp_path / "webui")
    recent, favorite = tmp_path / "recent", tmp_path / "favorite"
    recent.mkdir()
    favorite.mkdir()
    controller = workspaces.WebUIWorkspaceController(
        session_manager=None, default_workspace=tmp_path, default_restrict_to_workspace=True,
    )
    first_read, release_first, second_settled_or_waiting = (threading.Event() for _ in range(3))
    roles = {}
    read = workspaces.read_webui_workspace_state

    def delayed_read(**kwargs):
        state = read(**kwargs)
        if roles.get(threading.get_ident()) == "first" and not first_read.is_set():
            first_read.set()
            assert release_first.wait(3), "Test did not release the preference reader"
        return state

    @contextmanager
    def observed_transaction(paths, **kwargs):
        if roles.get(threading.get_ident()) == "second":
            second_settled_or_waiting.set()
        with file_write_transaction(paths, **kwargs):
            yield

    monkeypatch.setattr(workspaces, "read_webui_workspace_state", delayed_read)
    monkeypatch.setattr(workspaces, "file_write_transaction", observed_transaction, raising=False)

    def remember():
        roles[threading.get_ident()] = "first"
        workspaces.remember_webui_project(recent)

    def change_setting():
        roles[threading.get_ident()] = "second"
        try:
            if second_change == "mode":
                workspaces.write_webui_default_access_mode("review")
            else:
                controller.set_favorite_project(str(favorite), True)
        finally:
            second_settled_or_waiting.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(remember)
        try:
            assert first_read.wait(3)
            second = pool.submit(change_setting)
            # Without read/modify/write ownership the second change commits
            # first; with it, that writer announces its lock wait instead.
            assert second_settled_or_waiting.wait(3)
        finally:
            release_first.set()
        first.result()
        second.result()

    state = read()
    assert state["recent_projects"] == [str(recent)]
    assert state["default_access_mode"] == ("review" if second_change == "mode" else "default")
    assert state["favorite_projects"] == ([str(favorite)] if second_change == "favorite" else [])
