"""Large inputs, failed commits and Stop must not damage files or stall peers."""

import asyncio
import hashlib
import threading
import tracemalloc

import pytest
from cirno_core.agent.tools.apply_patch import ApplyPatchTool
from cirno_core.agent.tools.filesystem import EditFileTool, ReadFileTool, WriteFileTool
from cirno_core.agent.tools.filesystem.text_page import read_text_page, text_encoding


def test_large_line_page_keeps_bounded_memory_and_hashes_complete_file(tmp_path):
    target = tmp_path / "long.txt"
    block = "科研❄".encode() * 8192
    digest = hashlib.sha256()
    with target.open("wb") as output:
        for _ in range(256):
            output.write(block)
            digest.update(block)
        output.write(b"\nlast\n")
        digest.update(b"\nlast\n")

    tracemalloc.start()
    try:
        page = read_text_page(
            target,
            encoding="utf-8",
            offset=1,
            limit=2000,
            max_chars=128_000,
            max_bytes=100 * 1024 * 1024,
            cancelled=threading.Event(),
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < 4 * 1024 * 1024
    assert page.content_hash == digest.hexdigest()
    assert page.total_lines == 2
    assert page.truncated_line
    assert len(page.text) <= 128_000


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16", "utf-32", "latin-1"])
def test_paginated_encodings_and_chunk_boundary_line_endings(tmp_path, encoding):
    target = tmp_path / "boundaries.txt"
    text = "a" * 65535 + "\r\ncafé\r\n\nthird\u0085end"
    raw = text.encode(encoding)
    target.write_bytes(raw)
    selected_encoding = encoding if encoding == "latin-1" else text_encoding(raw[:32])
    page = read_text_page(
        target,
        encoding=selected_encoding,
        offset=2,
        limit=3,
        max_chars=128_000,
        max_bytes=1024 * 1024,
        cancelled=threading.Event(),
    )
    assert page.text == "2| café\n3| \n4| third"
    assert page.total_lines == len(text.splitlines())
    assert page.content_hash == hashlib.sha256(raw).hexdigest()


@pytest.mark.asyncio
async def test_stop_drains_read_worker_without_blocking_other_tasks(tmp_path, monkeypatch):
    from cirno_core.agent.tools.filesystem import read

    target = tmp_path / "read.txt"
    target.write_text("one\ntwo\n")
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    cancellation_seen = threading.Event()
    scan = read.read_text_page

    def slow_scan(*args, **kwargs):
        entered.set()
        try:
            assert release.wait(3), "test did not release the file reader"
            if kwargs["cancelled"].is_set():
                cancellation_seen.set()
            return scan(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(read, "read_text_page", slow_scan)
    task = asyncio.create_task(ReadFileTool(workspace=tmp_path).execute(path=str(target)))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "Stop returned with an unowned file reader still running"
        assert not finished.is_set()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert finished.is_set()
    assert cancellation_seen.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["write", "edit", "patch"])
async def test_failed_atomic_commit_preserves_original_and_permissions(
    tmp_path, monkeypatch, operation
):
    from cirno_core.utils import atomic_file

    target = tmp_path / "work.txt"
    target.write_bytes(b"before\r\n")
    target.chmod(0o640)

    def fail_replace(*args):
        raise OSError("disk commit failed")

    monkeypatch.setattr(atomic_file, "replace_atomic", fail_replace)
    if operation == "write":
        result = await WriteFileTool(workspace=tmp_path).execute(path=str(target), content="after")
    elif operation == "edit":
        result = await EditFileTool(workspace=tmp_path).execute(
            path=str(target),
            old_text="before",
            new_text="after",
        )
    else:
        result = await ApplyPatchTool(workspace=tmp_path).execute(
            edits=[
                {
                    "path": str(target),
                    "action": "replace",
                    "old_text": "before",
                    "new_text": "after",
                }
            ]
        )
    assert getattr(result, "is_error", False)
    assert "disk commit failed" in result
    assert target.read_bytes() == b"before\r\n"
    assert target.stat().st_mode & 0o777 == 0o640
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.asyncio
async def test_patch_reports_failed_rollback_and_continues_restoring_other_files(
    tmp_path, monkeypatch
):
    from cirno_core.agent.tools.filesystem import patch_plan

    for name in ("first.txt", "second.txt"):
        (tmp_path / name).write_text("before\n")
    write = patch_plan.atomic_write_text

    def fail_second(path, content):
        if path.name == "second.txt":
            if content == "after\n":
                write(path, content)
            raise OSError("second file is unavailable")
        write(path, content)

    monkeypatch.setattr(patch_plan, "atomic_write_text", fail_second)
    result = await ApplyPatchTool(workspace=tmp_path).execute(
        edits=[
            {"path": name, "action": "replace", "old_text": "before", "new_text": "after"}
            for name in ("first.txt", "second.txt")
        ]
    )
    assert getattr(result, "is_error", False)
    assert "could not restore files" in result
    assert "second.txt" in result
    assert (tmp_path / "first.txt").read_text() == "before\n"


@pytest.mark.asyncio
async def test_oversized_edit_batch_rejected_before_any_file_is_changed(tmp_path):
    # Original + updated snapshots exceed the batch budget, while each file fits.
    original = "a" * (1024 * 1024) + "\n"
    names = [f"part-{index}.txt" for index in range(4)]
    for name in names:
        (tmp_path / name).write_text(original)
    result = await ApplyPatchTool(workspace=tmp_path).execute(
        edits=[
            {
                "path": name,
                "action": "replace",
                "old_text": original,
                "new_text": original.replace("a", "b"),
            }
            for name in names
        ]
    )
    assert "8 MiB" in result
    assert all((tmp_path / name).read_text() == original for name in names)


@pytest.mark.asyncio
async def test_single_edit_rejects_large_file_without_reading_it_into_memory(tmp_path):
    target = tmp_path / "large.txt"
    with target.open("wb") as output:
        output.write(b"before\n")
        output.truncate(16 * 1024 * 1024)
    result = await EditFileTool(workspace=tmp_path).execute(
        path=str(target),
        old_text="before",
        new_text="after",
    )
    assert getattr(result, "is_error", False)
    assert "2 MiB" in result
    assert target.stat().st_size == 16 * 1024 * 1024
    with target.open("rb") as source:
        assert source.read(7) == b"before\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["edit", "patch"])
@pytest.mark.parametrize("stop", [False, True], ids=["concurrent-write", "stop"])
async def test_prepared_edit_cannot_commit_after_stop_or_overwrite_a_peer(
    tmp_path,
    monkeypatch,
    operation,
    stop,
):
    target = tmp_path / "work.txt"
    target.write_text("before\n")
    entered, release = threading.Event(), threading.Event()
    tool = (
        EditFileTool(workspace=tmp_path)
        if operation == "edit"
        else ApplyPatchTool(workspace=tmp_path)
    )
    method = "_prepare_edit" if operation == "edit" else "_prepare"
    prepare = getattr(tool, method)

    def paused_prepare(*args, **kwargs):
        result = prepare(*args, **kwargs)
        entered.set()
        assert release.wait(3), "test did not release preparation"
        return result

    monkeypatch.setattr(tool, method, paused_prepare)
    if operation == "edit":
        pending = tool.execute(path=str(target), old_text="before", new_text="after")
    else:
        pending = tool.execute(
            edits=[
                {
                    "path": str(target),
                    "action": "replace",
                    "old_text": "before",
                    "new_text": "after",
                }
            ]
        )
    task = asyncio.create_task(pending)
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        if stop:
            task.cancel()
            await asyncio.sleep(0)
        else:
            result = await WriteFileTool(workspace=tmp_path).execute(
                path=str(target), content="peer\n"
            )
            assert not getattr(result, "is_error", False)
    finally:
        release.set()
    if stop:
        with pytest.raises(asyncio.CancelledError):
            await task
        assert target.read_text() == "before\n"
    else:
        result = await task
        assert getattr(result, "is_error", False)
        assert "File changed while preparing" in result
        assert target.read_text() == "peer\n"


@pytest.mark.asyncio
async def test_many_exact_matches_do_not_retain_all_spans_or_copy_file_per_replacement(tmp_path):
    target = tmp_path / "repeated.txt"
    target.write_text("same " * 15_000 + "\n")
    tracemalloc.start()
    try:
        result = await EditFileTool(workspace=tmp_path).execute(
            path=str(target),
            old_text="same",
            new_text="new",
            replace_all=True,
            expected_replacements=15_000,
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert not getattr(result, "is_error", False)
    assert target.read_text() == "new " * 15_000 + "\n"
    assert peak < 4 * 1024 * 1024
