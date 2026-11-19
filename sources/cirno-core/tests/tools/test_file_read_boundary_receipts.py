"""File capability roots and alternate lookup destinations retain authorization."""

import pytest
from cirno_core.agent.tools.file_state import FileStates, file_read_context
from cirno_core.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from cirno_core.security.workspace_access import (
    bind_workspace_scope,
    build_workspace_scope,
    reset_workspace_scope,
)


async def test_standalone_explicit_allowed_directory_permits_its_own_files(tmp_path):
    target = tmp_path / "fixture.txt"
    target.write_text("allowed content")
    result = await ReadFileTool(allowed_dir=tmp_path).execute(path=str(target))
    assert "allowed content" in result
    assert not getattr(result, "is_error", False)


@pytest.mark.parametrize("mode", ["restricted", "full"])
async def test_normal_workspace_tools_follow_current_scope(tmp_path, mode):
    original, selected, outside = (tmp_path / name for name in ("original", "selected", "outside"))
    for directory in (original, selected, outside):
        directory.mkdir()
        (directory / "fixture.txt").write_text(directory.name)
    tool = ReadFileTool(workspace=original, allowed_dir=original)
    token = bind_workspace_scope(build_workspace_scope(selected, mode))
    try:
        result = await tool.execute(path="fixture.txt")
        assert "1| selected" in result
        other = await tool.execute(path=str(outside / "fixture.txt"))
        assert getattr(other, "is_error", False) is (mode == "restricted")
        if mode == "full":
            assert "1| outside" in other
    finally:
        reset_workspace_scope(token)


@pytest.mark.parametrize("operation", ["read", "list", "write"])
@pytest.mark.parametrize("scope", [None, "restricted", "full"])
async def test_standalone_explicit_allowed_directory_is_not_ignored(tmp_path, operation, scope):
    allowed, outside = tmp_path / "allowed", tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    target = outside / "target.txt"
    target.write_text("outside boundary fixture")
    token = bind_workspace_scope(build_workspace_scope(outside, scope)) if scope else None
    try:
        if operation == "read":
            result = await ReadFileTool(allowed_dir=allowed).execute(path=str(target))
        elif operation == "list":
            result = await ListDirTool(allowed_dir=allowed).execute(path=str(outside))
        else:
            result = await WriteFileTool(allowed_dir=allowed).execute(
                path=str(target), content="unexpected"
            )
        assert getattr(result, "is_error", False)
        assert "outside allowed directory" in result
        assert target.read_text() == "outside boundary fixture"
    finally:
        if token is not None:
            reset_workspace_scope(token)


@pytest.mark.parametrize("authorized", [False, True])
async def test_builtin_skill_fallback_rechecks_actual_destination(
    tmp_path, monkeypatch, authorized
):
    workspace, bundled = tmp_path / "project", tmp_path / "bundled"
    workspace.mkdir()
    skill = bundled / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("bundled fixture instructions")
    monkeypatch.setattr("cirno_core.skills.metadata.BUILTIN_SKILLS_DIR", bundled)
    tool = ReadFileTool(
        workspace=workspace,
        allowed_dir=workspace,
        extra_read_allowed_dirs=[bundled] if authorized else [],
    )
    result = await tool.execute(path="skills/demo/SKILL.md")
    assert getattr(result, "is_error", False) is not authorized
    if authorized:
        assert "bundled fixture instructions" in result
    else:
        assert "outside allowed directory" in result
        assert "bundled fixture instructions" not in result


@pytest.mark.parametrize("operation", ["write", "edit"])
@pytest.mark.parametrize("published", [False, True])
async def test_failed_atomic_publication_explicitly_reports_uncertain_outcome(
    tmp_path, monkeypatch, operation, published
):
    from cirno_core.utils import atomic_file

    target = tmp_path / "target.txt"
    target.write_text("before\n")
    states = FileStates()
    reader = ReadFileTool(workspace=tmp_path, file_states=states)
    with file_read_context("first", lambda: {}):
        first = await reader.execute(path=str(target))
    replace = atomic_file.replace_atomic

    def fail_replace(source, destination):
        if published:
            replace(source, destination)
        raise OSError("fixture persistence failure")

    monkeypatch.setattr(atomic_file, "replace_atomic", fail_replace)
    if operation == "write":
        result = await WriteFileTool(workspace=tmp_path, file_states=states).execute(
            path=str(target), content="after\n"
        )
    else:
        result = await EditFileTool(workspace=tmp_path, file_states=states).execute(
            path=str(target), old_text="before", new_text="after"
        )
    assert getattr(result, "is_error", False)
    assert "outcome unconfirmed" in result
    assert "Read it before retrying" in result
    assert target.read_text() == ("after\n" if published else "before\n")
    with file_read_context("next", lambda: {"first": first}):
        observed = await reader.execute(path=str(target))
    if published:
        assert "after" in observed and "unchanged" not in observed.lower()
