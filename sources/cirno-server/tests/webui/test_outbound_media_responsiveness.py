"""Media projection preserves replies and settles owned work before cancellation."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.security.workspace_access import WorkspaceScopeError, build_workspace_scope
from cirno_server.webui.outbound_delivery import WebUIOutboundDelivery


def delivery(tmp_path, rewrite, reader=None):
    return WebUIOutboundDelivery(
        SimpleNamespace(),
        media=SimpleNamespace(workspace_path=tmp_path, rewrite_local_markdown_images=rewrite),
        transcripts=None, temporary_chats=None, session_projection=None,
        workspaces=SimpleNamespace(async_scope_for_session_key=reader) if reader is not None else None,
    )


async def test_markdown_media_projection_does_not_block_and_drains_cancel(tmp_path):
    entered, finished, release = (threading.Event() for _ in range(3))

    def slow_rewrite(text, **kwargs):
        entered.set()
        try:
            release.wait(1)
            return "rewritten"
        finally:
            finished.set()

    output = delivery(tmp_path, slow_rewrite)
    task = asyncio.create_task(output._rewrite_markdown_media("slow-media", "![plot](plot.png)"))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        assert not finished.is_set(), "Media copy blocked event-loop progress"
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "An owned media copy outlived cancellation"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("failure", ["policy", "file"])
async def test_unavailable_markdown_media_does_not_lose_the_reply(tmp_path, failure):
    def unavailable(text, **kwargs):
        if failure == "policy":
            pytest.fail("Invalid policy must not fall back to default workspace media")
        raise OSError("image unavailable")

    reader = AsyncMock(
        side_effect=WorkspaceScopeError("invalid scope") if failure == "policy" else None,
        return_value=build_workspace_scope(tmp_path, "restricted"),
    )
    output = delivery(tmp_path, unavailable, reader)
    text = "Keep this answer. ![plot](plot.png)"
    assert await output._rewrite_markdown_media("unavailable-media", text) == text
