"""Filesystem search must report failed scans and never block on special files."""

import errno
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.search import FindFilesTool, GrepTool


@pytest.mark.parametrize("tool_class", [FindFilesTool, GrepTool])
@pytest.mark.parametrize("nested", [False, True])
async def test_unreadable_directory_is_an_error(tmp_path, monkeypatch, tool_class, nested):
    blocked = tmp_path / "blocked" if nested else tmp_path
    blocked.mkdir(exist_ok=True)
    (tmp_path / "visible.txt").write_text("needle")
    scandir = os.scandir

    def scan(path):
        if Path(path) == blocked:
            raise PermissionError(errno.EACCES, "Cannot scan directory", str(blocked))
        return scandir(path)

    monkeypatch.setattr(os, "scandir", scan)
    args = {"pattern": "needle"} if tool_class is GrepTool else {}
    result = await tool_class(workspace=tmp_path).execute(**args)

    assert is_tool_error_result(result)
    assert str(blocked) in result and "Cannot scan directory" in result
    assert "No files found" not in result and "No matches found" not in result


@pytest.mark.parametrize("tool_class", [FindFilesTool, GrepTool])
async def test_entry_metadata_failure_is_an_error(tmp_path, monkeypatch, tool_class):
    def fail(**kwargs):
        raise OSError(errno.EIO, "Cannot classify entry", str(tmp_path / "entry"))

    @contextmanager
    def scan(path):
        yield iter([SimpleNamespace(is_dir=fail)])

    monkeypatch.setattr(os, "scandir", scan)
    args = {"pattern": "needle"} if tool_class is GrepTool else {}
    result = await tool_class(workspace=tmp_path).execute(**args)

    assert is_tool_error_result(result)
    assert "Cannot classify entry" in result


@pytest.mark.parametrize("tool_class", [FindFilesTool, GrepTool])
async def test_file_stat_failure_is_not_binary_or_zero_mtime(tmp_path, monkeypatch, tool_class):
    target = tmp_path / "data.txt"
    target.write_text("needle")
    original = Path.stat

    def stat(path, **kwargs):
        if path == target:
            raise OSError(errno.EIO, "Cannot stat search result", str(target))
        return original(path, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    args = {"pattern": "needle"} if tool_class is GrepTool else {"sort": "modified"}
    result = await tool_class(workspace=tmp_path).execute(**args)

    assert is_tool_error_result(result)
    assert "Cannot stat search result" in result
    assert "binary" not in result


async def test_file_read_failure_is_visible(tmp_path, monkeypatch):
    target = tmp_path / "data.txt"
    target.write_text("needle")
    original = Path.open

    def open_file(path, *args, **kwargs):
        if path == target:
            raise PermissionError(errno.EACCES, "Cannot read search result", str(target))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_file)
    result = await GrepTool(workspace=tmp_path).execute(pattern="needle")

    assert is_tool_error_result(result)
    assert "Cannot read search result" in result


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Requires POSIX named pipes")
async def test_named_pipe_is_not_opened(tmp_path, monkeypatch):
    pipe = tmp_path / "events.txt"
    os.mkfifo(pipe)
    (tmp_path / "data.txt").write_text("needle")
    original = Path.open

    def open_file(path, *args, **kwargs):
        assert path != pipe, "Searching a FIFO must not wait for a writer"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_file)
    result = await GrepTool(workspace=tmp_path).execute(pattern="needle")

    assert "data.txt:1" in result
    assert "skipped 1 non-regular files" in result
    assert not is_tool_error_result(result)


@pytest.mark.parametrize("restricted", [True, False])
async def test_file_symlink_obeys_workspace_policy(tmp_path, restricted, create_symlink):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("needle secret")
    create_symlink(workspace / "link.txt", outside)
    result = await GrepTool(workspace=workspace, restrict_to_workspace=restricted).execute(
        pattern="needle",
    )

    if restricted:
        assert is_tool_error_result(result)
        assert "needle secret" not in result
    else:
        assert "link.txt:1" in result and "needle secret" in result


@pytest.mark.parametrize("tool_class", [FindFilesTool, GrepTool])
async def test_directory_symlink_is_not_followed(tmp_path, tool_class, create_symlink):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("needle secret")
    create_symlink(workspace / "external", outside, target_is_directory=True)
    args = {"pattern": "needle"} if tool_class is GrepTool else {}
    result = await tool_class(workspace=workspace, restrict_to_workspace=True).execute(**args)

    assert "secret" not in result
    assert not is_tool_error_result(result)


async def test_document_failures_are_reported_separately_from_binary_files(tmp_path, monkeypatch):
    for number in range(12):
        (tmp_path / f"{number:02}.pdf").write_bytes(b"invalid PDF")
    (tmp_path / "data.txt").write_text("needle")

    def open_document(*args, **kwargs):
        raise ValueError("Invalid PDF")

    monkeypatch.setattr(
        "cirno_core.agent.tools.search.sources.open_document_line_source", open_document,
    )
    result = await GrepTool(workspace=tmp_path).execute(pattern="needle")

    assert "data.txt:1" in result
    assert "could not search 12 documents; first document error: 00.pdf: Invalid PDF" in result
    assert "binary" not in result
