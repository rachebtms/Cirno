"""Stopping file tools must settle accepted writes without abandoned workers."""

import asyncio
from threading import Event

import pytest

from cirno_core.agent.tools.apply_patch import ApplyPatchTool
from cirno_core.agent.tools.filesystem import WriteFileTool
from cirno_core.utils.file_transactions import file_write_transaction


async def wait(event: Event) -> None:
    assert await asyncio.wait_for(asyncio.to_thread(event.wait, 4), 5)


@pytest.mark.asyncio
async def test_stopping_a_write_waiting_for_ownership_does_not_write_after_release(
    tmp_path, monkeypatch
):
    from cirno_core.agent.tools.filesystem import write

    path = tmp_path / "shared.txt"
    path.write_text("original")
    held, release, scheduled = Event(), Event(), Event()

    def hold():
        with file_write_transaction([path]):
            held.set()
            assert release.wait(5)

    operation = write.run_file_operation

    async def observed_operation(callback):
        def observe(cancelled):
            scheduled.set()
            return callback(cancelled)

        return await operation(observe)

    monkeypatch.setattr(write, "run_file_operation", observed_operation)
    owner = asyncio.create_task(asyncio.to_thread(hold))
    task = None
    try:
        await wait(held)
        task = asyncio.create_task(
            WriteFileTool(workspace=tmp_path).execute(path=str(path), content="late write")
        )
        await wait(scheduled)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert not owner.done()
        assert path.read_text() == "original"
    finally:
        release.set()
        await owner
        if task is not None:
            with pytest.raises(asyncio.CancelledError):
                await task
    assert path.read_text() == "original"


@pytest.mark.asyncio
async def test_stopping_an_accepted_batch_waits_for_the_complete_batch(tmp_path, monkeypatch):
    from cirno_core.agent.tools.filesystem import patch_plan

    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    first.write_text("original")
    second.write_text("original")
    published, release = Event(), Event()
    write = patch_plan.atomic_write_text

    def pause_after_first(path, content):
        write(path, content)
        if path == first:
            published.set()
            assert release.wait(5)

    monkeypatch.setattr(patch_plan, "atomic_write_text", pause_after_first)
    task = asyncio.create_task(
        ApplyPatchTool(workspace=tmp_path).execute(
            edits=[
                {
                    "path": str(first),
                    "action": "replace",
                    "old_text": "original",
                    "new_text": "changed",
                },
                {
                    "path": str(second),
                    "action": "replace",
                    "old_text": "original",
                    "new_text": "changed",
                },
            ]
        )
    )
    try:
        await wait(published)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert second.read_text() == "original"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert first.read_text() == second.read_text() == "changed\n"
