from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _provider() -> MagicMock:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation = SimpleNamespace(
        max_tokens=4096,
        temperature=0.1,
        reasoning_effort=None,
    )
    return provider


def test_request_concurrency_is_unlimited_by_default(
    monkeypatch: pytest.MonkeyPatch,
    loop_factory,
) -> None:
    monkeypatch.delenv("CIRNO_MAX_CONCURRENT_REQUESTS", raising=False)

    loop = loop_factory(provider=_provider(), patch_deps=True)

    assert loop._concurrency_gate is None


@pytest.mark.asyncio
async def test_positive_request_concurrency_keeps_explicit_cap(
    monkeypatch: pytest.MonkeyPatch,
    loop_factory,
) -> None:
    monkeypatch.setenv("CIRNO_MAX_CONCURRENT_REQUESTS", "2")
    loop = loop_factory(provider=_provider(), patch_deps=True)
    gate = loop._concurrency_gate

    assert gate is not None
    for _ in range(2):
        await gate.acquire()
    try:
        assert gate.locked()
    finally:
        for _ in range(2):
            gate.release()


async def test_cirno_keeps_reserved_capacity_and_lists_running_and_queued_workers(monkeypatch, loop_factory):
    import asyncio
    import json
    from unittest.mock import AsyncMock
    from cirno_core.agent.tools.context import RequestContext, request_context
    from cirno_core.bus.events import InboundMessage
    from cirno_core.session.keys import ROUTER_CHAT_ID, ROUTER_SESSION_KEY

    monkeypatch.setenv("CIRNO_MAX_CONCURRENT_REQUESTS", "1")
    provider = _provider()
    provider.aclose = AsyncMock()
    loop = loop_factory(provider=provider)
    started = {name: asyncio.Event() for name in ("worker-a", "worker-b", ROUTER_CHAT_ID)}
    release = asyncio.Event()

    async def execute(message, **kwargs):
        started[message.chat_id].set()
        await release.wait()
        return None
    monkeypatch.setattr(loop.processing, "process", execute)
    try:
        for name in started:
            await loop.sessions.state.get("websocket:" + name)
        for name in ("worker-a", "worker-b", ROUTER_CHAT_ID):
            await loop.dispatch.enqueue(InboundMessage(channel="websocket", chat_id=name, sender_id="user", content="Run"))
        await asyncio.wait_for(started["worker-a"].wait(), 3)
        await asyncio.wait_for(started[ROUTER_CHAT_ID].wait(), 3)
        assert not started["worker-b"].is_set()
        source = await loop.sessions.state.read_header(ROUTER_SESSION_KEY)
        with request_context(RequestContext(channel="websocket", chat_id="b1ec9323-2155-5f24-bc56-1da2f59aeecb", session_key=ROUTER_SESSION_KEY,
                                            session_generation=source.generation)):
            result = json.loads(await loop.tools.get("control_session").execute(action="list"))
        assert result["worker_concurrency_limit"] == 1 and result["router_has_reserved_slot"] is True
        assert result["subagent_concurrency_limit"] == loop.subagents.max_concurrent_subagents
        states = {row["session_key"]: row["execution_status"] for row in result["conversations"]}
        assert states == {"websocket:worker-a": "running", "websocket:worker-b": "queued", ROUTER_SESSION_KEY: "running"}
        assert next(row for row in result["conversations"] if row["session_key"] == ROUTER_SESSION_KEY)["handle"] == "@cirno"
        release.set()
        await asyncio.wait_for(started["worker-b"].wait(), 3)
    finally:
        release.set()
        await loop.aclose()
