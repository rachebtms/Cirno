"""File activity observes bounded snapshots without executing write-side work."""

import os
import threading
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.agent.hooks import FileEditActivityHook
from cirno_core.agent.tools.apply_patch import ApplyPatchTool
from cirno_core.agent.tools.file_state import FileStates
from cirno_core.agent.tools.filesystem import EditFileTool, WriteFileTool
from cirno_core.bus.agent_events import EventSink
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_core.utils.file_edit_events import prepare_file_edit_trackers, read_file_snapshot


def test_activity_snapshot_detects_growth_after_size_check(tmp_path, monkeypatch):
    path = tmp_path / "target.txt"
    path.write_bytes(b"longer than eight bytes")
    stat = Path.stat

    def stale_stat(self, *args, **kwargs):
        result = stat(self, *args, **kwargs)
        if self == path:
            values = list(result)
            values[6] = 1
            return os.stat_result(values)
        return result

    monkeypatch.setattr(Path, "stat", stale_stat)
    snapshot = read_file_snapshot(path, max_bytes=8)
    assert snapshot.oversized
    assert not snapshot.countable
    assert snapshot.text is None


def test_activity_path_lookup_does_not_capture_skill_history(tmp_path, monkeypatch):
    path = tmp_path / "target.txt"
    path.write_text("before\n")
    capture = Mock()
    monkeypatch.setattr("cirno_core.skills.history.capture_skill_path", capture)
    assert prepare_file_edit_trackers(
        call_id="edit",
        tool_name="edit_file",
        tool=EditFileTool(workspace=tmp_path),
        workspace=tmp_path,
        params={"path": path.name, "old_text": "before", "new_text": "after"},
    )
    capture.assert_not_called()


async def test_activity_snapshot_and_diff_work_runs_off_the_event_loop(tmp_path, monkeypatch):
    from cirno_core.agent.hooks import file_edit_activity as activity

    path = tmp_path / "target.txt"
    path.write_text("before\n")
    owner_thread = threading.get_ident()
    prepare, finish = activity.prepare_file_edit_trackers, activity.build_file_edit_end_event

    def prepare_owned(**kwargs):
        assert threading.get_ident() != owner_thread
        return prepare(**kwargs)

    def finish_owned(*args, **kwargs):
        assert threading.get_ident() != owner_thread
        return finish(*args, **kwargs)

    monkeypatch.setattr(activity, "prepare_file_edit_trackers", prepare_owned)
    monkeypatch.setattr(activity, "build_file_edit_end_event", finish_owned)
    publish = AsyncMock()
    hook = FileEditActivityHook(events=EventSink(publish), workspace=tmp_path)
    tool = EditFileTool(workspace=tmp_path)
    params = {"path": path.name, "old_text": "before", "new_text": "after"}
    call = ToolCallRequest(id="edit", name="files__edit", arguments=params)
    await hook.before_execute_tool(None, call, tool, params)
    result = await tool.execute(**params)
    await hook.after_execute_tool(None, call, tool, params, result)
    assert [entry.args[0].file_edit_events[0]["status"] for entry in publish.await_args_list] == [
        "editing",
        "done",
    ]


@pytest.mark.parametrize("operation", ["write", "edit", "patch"])
async def test_skill_postwrite_capture_finishes_in_the_file_worker(
    tmp_path, monkeypatch, operation
):
    path = tmp_path / "home" / "skills" / "demo" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("before\n")
    owner_thread = threading.get_ident()
    captures = []

    def capture(resolved, home=None):
        assert threading.get_ident() != owner_thread
        captures.append(resolved)

    monkeypatch.setattr("cirno_core.skills.history.capture_skill_path", capture)
    if operation == "write":
        result = await WriteFileTool(workspace=tmp_path).execute(path=str(path), content="after\n")
    elif operation == "edit":
        result = await EditFileTool(workspace=tmp_path).execute(
            path=str(path), old_text="before", new_text="after"
        )
    else:
        result = await ApplyPatchTool(workspace=tmp_path).execute(
            edits=[
                {"path": str(path), "action": "replace", "old_text": "before", "new_text": "after"},
            ]
        )
    assert not getattr(result, "is_error", False)
    assert path.read_text() == "after\n"
    assert captures == [path, path]


@pytest.mark.parametrize("operation", ["write", "edit", "patch"])
async def test_failed_postwrite_history_explicitly_reports_saved_content_and_retires_read_cache(
    tmp_path, monkeypatch, operation
):
    path = tmp_path / "target.txt"
    path.write_text("before\n")
    states = FileStates()
    states.record_read(path, content_hash="original", result="before")
    captures = 0

    def capture(_path, home=None):
        nonlocal captures
        captures += 1
        if captures == 2:
            raise OSError("fixture history unavailable")

    monkeypatch.setattr("cirno_core.skills.history.capture_skill_path", capture)
    options = {"workspace": tmp_path, "file_states": states}
    if operation == "write":
        result = await WriteFileTool(**options).execute(path=path.name, content="after\n")
    elif operation == "edit":
        result = await EditFileTool(**options).execute(
            path=path.name, old_text="before", new_text="after"
        )
    else:
        result = await ApplyPatchTool(**options).execute(
            edits=[
                {"path": path.name, "action": "replace", "old_text": "before", "new_text": "after"},
            ]
        )
    assert getattr(result, "is_error", False)
    assert "contents were saved" in result
    assert "Do not repeat" in result
    assert path.read_text() == "after\n"
    assert states.get(path) is None


async def test_failed_history_capture_still_retires_every_committed_patch_receipt(
    tmp_path, monkeypatch
):
    paths = [tmp_path / "first.txt", tmp_path / "second.txt"]
    states = FileStates()
    for path in paths:
        path.write_text("before\n")
        states.record_read(path, content_hash="original", result="before")
    captures = []

    def capture(path, home=None):
        captures.append(path)
        if len(captures) == 3:
            raise OSError("fixture first postwrite capture failed")

    monkeypatch.setattr("cirno_core.skills.history.capture_skill_path", capture)
    result = await ApplyPatchTool(workspace=tmp_path, file_states=states).execute(
        edits=[
            {"path": path.name, "action": "replace", "old_text": "before", "new_text": "after"}
            for path in paths
        ]
    )
    assert getattr(result, "is_error", False)
    assert "contents were saved" in result
    assert captures == [*paths, *paths]
    for path in paths:
        assert path.read_text() == "after\n"
        assert states.get(path) is None
