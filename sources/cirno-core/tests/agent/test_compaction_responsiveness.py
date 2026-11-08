"""Slow checkpoint storage must not stall the shared server event loop."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.memory.archiver import MemoryArchiver
from cirno_core.memory.store import MemoryStore
from cirno_memory.repository import MemoryRepository
from cirno_core.memory.working_state import EvidenceCheckpoint
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.generation import GenerationSettings
from cirno_core.session.model import Session
from cirno_core.utils.llm_runtime import LLMRuntime


@pytest.mark.parametrize("path", ["summary", "provider_failure", "no_input_budget"])
async def test_slow_checkpoint_write_keeps_other_sessions_responsive(tmp_path, monkeypatch, path):
    store = MemoryStore(tmp_path)
    provider = MagicMock(spec=LLMProvider)
    provider.chat_stream_with_retry = AsyncMock(
        return_value=LLMResponse(content="Verified result: run 17 succeeded; continue with run 18.")
    )
    if path == "provider_failure":
        provider.chat_stream_with_retry.side_effect = ConnectionError("provider unavailable")
    runtime = LLMRuntime(provider, "test", GenerationSettings(max_tokens=2048), 32000)
    messages = [{"role": "user", "content": "Continue calibration after run 17"}]
    archiver = MemoryArchiver(store, lambda **kwargs: [], lambda _: [])
    started, release = threading.Event(), threading.Event()
    append = store.journal.append_record

    def slow_append(*args, **kwargs):
        started.set()
        release.wait()
        return append(*args, **kwargs)

    monkeypatch.setattr(store.journal, "append_record", slow_append)
    # Release even an old implementation that blocks the event loop, so failure
    # is bounded and never leaves pytest waiting on an executor thread.
    watchdog = threading.Timer(3, release.set)
    watchdog.start()
    if path == "no_input_budget":
        pending = archiver.archive_session(
            Session(key="test:calibration", messages=messages),
            archive_end=1, runtime=runtime, input_token_budget=0,
        )
    else:
        pending = archiver.archive(
            messages, runtime=runtime, session_key="test:calibration",
            history=messages, request_tools=[],
        )
    task = asyncio.create_task(pending)
    try:
        assert await asyncio.wait_for(asyncio.to_thread(started.wait, 1), 2)
        assert not release.is_set(), "checkpoint I/O stalled the shared event loop"
        other_session = asyncio.create_task(asyncio.sleep(0, result="other session responded"))
        assert await other_session == "other session responded"
        assert not task.done()
    finally:
        release.set()
        watchdog.cancel()
        checkpoint = await task
    assert checkpoint
    assert isinstance(checkpoint, EvidenceCheckpoint) == (path != "summary")
    reopened = MemoryStore(tmp_path)
    assert reopened.journal.read_unprocessed_history(0)[0]["session_key"] == "test:calibration"
    with MemoryRepository(tmp_path).connect() as db:
        assert db.execute("SELECT count(*) FROM memories WHERE layer='task'").fetchone()[0] > 0
