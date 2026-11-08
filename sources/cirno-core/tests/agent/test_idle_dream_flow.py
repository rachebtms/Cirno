"""An idle batch runs real restricted tools and acknowledges persisted evidence."""

import asyncio
import json
import re
import time
from unittest.mock import AsyncMock

from cirno_core.agent.loop import AgentLoop
from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_core.memory.dream_run import run_dream
from cirno_core.memory.idle import MemoryIdleCoordinator
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_memory.repository import MemoryRepository


class DreamProvider(LLMProvider):
    def __init__(self):
        super().__init__(provider_name="dream-fixture")

    def get_default_model(self):
        return "fixture"

    async def chat(self, messages, **kwargs):
        raise AssertionError("Use the deterministic streaming fixture")


async def test_idle_dream_distills_confirms_and_does_not_reprocess_its_input(tmp_path):
    provider = DreamProvider()
    bus = MessageBus()
    loop = AgentLoop(bus=bus, provider=provider, workspace=tmp_path / "workspace")
    store = loop.context.memory
    session_key = "websocket:64a317ed-65a7-4575-a5a5-0fb6d0f02af4"
    cursor = store.journal.append_history(
        "Measured calibration sample A: 43.2 at 280 K.", session_key=session_key
    )
    source_id, source_revision, knowledge_id = None, None, None
    calls = 0

    async def respond(**kwargs):
        nonlocal calls, source_id, source_revision, knowledge_id
        calls += 1
        names = {item["function"]["name"] for item in kwargs["tools"]}
        assert (
            "memory__confirm" in names
            and "shell__exec" not in names
            and "user__message" not in names
        )
        if calls == 1:
            inputs = re.findall(
                r"\[Memory ID: ([^;]+); revision: (\d+);", kwargs["messages"][-1]["content"]
            )
            assert len(inputs) == 1
            source_id, revision = inputs[0]
            source_revision = int(revision)
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        "distill",
                        "memory__save",
                        {
                            "content": "Calibration sample A measured 43.2 at 280 K.",
                            "source": "memory:" + source_id,
                            "based_on": source_id,
                            "kind": "fact",
                            "layer": "knowledge",
                            "title": "Calibration measurement",
                        },
                    )
                ],
            )
        result = json.loads(kwargs["messages"][-1]["content"])
        if calls == 2:
            knowledge_id = result["id"]
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        "receipt",
                        "memory__confirm",
                        {
                            "memory_id": source_id,
                            "input_revision": source_revision,
                            "outcome": "created",
                            "target_ids": [knowledge_id],
                            "reason": "Stored the measured value with its original source and units.",
                        },
                    )
                ],
            )
        assert calls == 3 and result["outcome"] == "created"
        return LLMResponse(content="Dream complete")

    provider.chat_stream_with_retry = AsyncMock(side_effect=respond)
    results = []

    async def consolidate():
        results.append(await run_dream(loop, commit_subject="dream: idle acceptance"))

    config = Config.model_validate(
        {
            "agents": {
                "defaults": {"dream": {"enabled": True, "mode": "idle", "idleAfterSeconds": 10}}
            }
        }
    )
    idle = MemoryIdleCoordinator(loop, config, consolidate)
    loop._last_memory_activity = time.monotonic() - 11
    try:
        await idle.check()
        assert loop._idle_memory_task is not None
        await asyncio.wait_for(loop._idle_memory_task, 10)
        assert len(results) == 1 and results[0].status == "completed"
        assert store.journal.get_last_dream_cursor() == cursor
        repo = MemoryRepository(store.workspace)
        saved = repo.read(knowledge_id, session_key=session_key)
        assert saved["based_on"] == source_id and saved["based_on_revision"] == source_revision
        assert saved["layer"] == "knowledge" and "43.2 at 280 K" in saved["content"]
        with repo.connect() as db:
            assert db.execute("SELECT count(*) FROM dream_queue").fetchone()[0] == 0
            receipt = dict(db.execute("SELECT * FROM dream_receipts").fetchone())
        assert receipt["memory_id"] == source_id and receipt["outcome"] == "created"
        assert json.loads(receipt["targets"])[0]["id"] == knowledge_id
        await asyncio.sleep(0)
        idle.next_dream = 0
        loop._last_memory_activity = time.monotonic() - 11
        await idle.check()
        await asyncio.wait_for(loop._idle_memory_task, 10)
        assert results[-1].status == "empty" and calls == 3
        assert bus.outbound_size == 0
    finally:
        await loop.aclose()
