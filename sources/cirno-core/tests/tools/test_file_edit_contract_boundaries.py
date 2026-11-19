"""File-edit refusals and previews must match their actual filesystem effects."""

import pytest
from cirno_core.agent.tools.apply_patch import ApplyPatchTool
from cirno_core.agent.tools.filesystem import EditFileTool


@pytest.mark.parametrize(
    "parameters",
    [
        {"replace_all": True, "occurrence": 1},
        {"replace_all": True, "line_hint": 1},
        {"occurrence": 1, "line_hint": 1},
        {"expected_replacements": 2},
        {"occurrence": 2},
        {"line_hint": 2},
    ],
)
@pytest.mark.parametrize("exists", [False, True])
async def test_create_semantics_cannot_skip_selection_guards(tmp_path, exists, parameters):
    path = tmp_path / "target.txt"
    if exists:
        path.write_text("")
    result = await EditFileTool(workspace=tmp_path).execute(
        path=path.name,
        old_text="",
        new_text="new",
        **parameters,
    )
    assert getattr(result, "is_error", False)
    assert path.read_text() == "" if exists else not path.exists()


async def test_ambiguous_edit_is_a_structured_failure_without_a_write(tmp_path):
    path = tmp_path / "target.txt"
    path.write_text("repeat\nrepeat\n")
    result = await EditFileTool(workspace=tmp_path).execute(
        path=path.name,
        old_text="repeat",
        new_text="changed",
    )
    assert getattr(result, "is_error", False)
    assert "appears 2 times" in result
    assert path.read_text() == "repeat\nrepeat\n"


async def test_patch_dry_run_does_not_create_skill_history(tmp_path, monkeypatch):
    home = tmp_path / "home"
    directory = home / "skills" / "demo"
    directory.mkdir(parents=True)
    path = directory / "SKILL.md"
    original = "---\nname: demo\ndescription: fixture\n---\n# Original\n"
    path.write_text(original)
    monkeypatch.setattr("cirno_core.skills.history.get_home_path", lambda: home)
    result = await ApplyPatchTool(workspace=home).execute(
        edits=[
            {
                "path": str(path),
                "action": "replace",
                "old_text": "# Original",
                "new_text": "# Changed",
            }
        ],
        dry_run=True,
    )
    assert "dry-run succeeded" in result
    assert path.read_text() == original
    assert not (home / "skills-history").exists()


@pytest.mark.parametrize("tool", ["edit", "patch"])
async def test_inline_edit_preserves_unselected_mixed_line_endings(tmp_path, tool):
    path = tmp_path / "target.txt"
    original = b"first\r\ntarget\nlast\r\n"
    path.write_bytes(original)
    if tool == "edit":
        result = await EditFileTool(workspace=tmp_path).execute(
            path=path.name, old_text="target", new_text="changed"
        )
    else:
        result = await ApplyPatchTool(workspace=tmp_path).execute(
            edits=[
                {
                    "path": path.name,
                    "action": "replace",
                    "old_text": "target",
                    "new_text": "changed",
                },
            ]
        )
    assert not getattr(result, "is_error", False)
    assert path.read_bytes() == original.replace(b"target", b"changed")


@pytest.mark.parametrize("tool", ["edit", "patch"])
@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
async def test_multiline_replacement_uses_target_line_ending_without_changing_neighbors(
    tmp_path, tool, ending
):
    path = tmp_path / "target.txt"
    other = b"\r\n" if ending == b"\n" else b"\n"
    original = b"first" + other + b"target" + ending + b"body" + other + b"last" + ending
    path.write_bytes(original)
    if tool == "edit":
        result = await EditFileTool(workspace=tmp_path).execute(
            path=path.name, old_text="target\nbody", new_text="changed\nextra\nbody"
        )
    else:
        result = await ApplyPatchTool(workspace=tmp_path).execute(
            edits=[
                {
                    "path": path.name,
                    "action": "replace",
                    "old_text": "target\nbody",
                    "new_text": "changed\nextra\nbody",
                },
            ]
        )
    assert not getattr(result, "is_error", False)
    assert path.read_bytes() == original.replace(
        b"target" + ending + b"body", b"changed" + ending + b"extra" + ending + b"body"
    )


async def test_replace_all_keeps_each_matches_local_line_ending(tmp_path):
    path = tmp_path / "target.txt"
    path.write_bytes(b"target\r\nkeep\ntarget\n")
    result = await EditFileTool(workspace=tmp_path).execute(
        path=path.name,
        old_text="target",
        new_text="changed\nextra",
        replace_all=True,
        expected_replacements=2,
    )
    assert not getattr(result, "is_error", False)
    assert path.read_bytes() == b"changed\r\nextra\r\nkeep\nchanged\nextra\n"


@pytest.mark.parametrize("exists", [False, True])
async def test_create_accepts_one_expected_replacement_and_keeps_provided_bytes(tmp_path, exists):
    path = tmp_path / "target.txt"
    if exists:
        path.touch()
    result = await EditFileTool(workspace=tmp_path).execute(
        path=path.name,
        old_text="",
        new_text="first\r\nlast\r\n",
        expected_replacements=1,
    )
    assert not getattr(result, "is_error", False)
    assert path.read_bytes() == b"first\r\nlast\r\n"


@pytest.mark.parametrize("ambiguous", [False, True])
async def test_public_edit_tool_and_activity_agree_on_success_or_refusal(tmp_path, ambiguous):
    from cirno_core.agent.hooks import FileEditActivityHook
    from cirno_core.agent.tools.execution import execute_tool_calls
    from cirno_core.agent.tools.registry import ToolRegistry
    from cirno_core.bus.agent_events import EventSink
    from cirno_core.providers.tool_calls import ToolCallRequest

    path = tmp_path / "target.txt"
    original = b"target\r\nkeep\ntarget\n" if ambiguous else b"target\r\nkeep\n"
    path.write_bytes(original)
    registry = ToolRegistry()
    registry.register(EditFileTool(workspace=tmp_path))
    notifications = []

    async def publish(event):
        notifications.extend(event.file_edit_events)

    hook = FileEditActivityHook(events=EventSink(publish), workspace=tmp_path)
    results, events = await execute_tool_calls(
        registry,
        [
            ToolCallRequest(
                id="edit",
                name="files__edit",
                arguments={
                    "path": path.name,
                    "old_text": "target",
                    "new_text": "changed",
                },
            )
        ],
        concurrent=False,
        external_lookup_counts={},
        workspace_violation_counts={},
        hook=hook,
        context=None,
    )
    assert events[0]["status"] == ("error" if ambiguous else "ok")
    assert [item["status"] for item in notifications] == [
        "editing",
        "error" if ambiguous else "done",
    ]
    assert not hook._trackers_by_call
    if ambiguous:
        assert path.read_bytes() == original
        assert "appears 2 times" in results[0]
    else:
        assert path.read_bytes() == original.replace(b"target", b"changed")
        assert (notifications[-1]["added"], notifications[-1]["deleted"]) == (1, 1)
