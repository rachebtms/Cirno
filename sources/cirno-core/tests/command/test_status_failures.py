"""Status queries must expose broken data sources instead of reporting success."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.bus.events import InboundMessage
from cirno_core.command.builtin.service import cmd_status
from cirno_core.command.router import CommandContext
from cirno_core.session.model import Session


@pytest.mark.parametrize("source", ["context", "search", "subagents"])
async def test_status_propagates_failed_data_source(source, monkeypatch):
    session = Session(key="cli:status")
    loop = MagicMock()
    loop.consolidator.estimate_session_prompt_tokens.return_value = (100, "test")
    loop.subagents.get_running_count_by_session.return_value = 0
    loop._active_tasks = {}
    loop._start_time = time.time()
    runtime = SimpleNamespace(
        model="test-model",
        context_window_tokens=128_000,
        generation=SimpleNamespace(max_tokens=100),
    )
    fetch_usage = AsyncMock(return_value=SimpleNamespace(format=lambda: "search usage"))
    monkeypatch.setattr("cirno_core.command.builtin.service.fetch_search_usage", fetch_usage)
    failure = RuntimeError(f"{source} data source failed")
    if source == "context":
        loop.consolidator.estimate_session_prompt_tokens.side_effect = failure
    elif source == "search":
        fetch_usage.side_effect = failure
    else:
        loop.subagents.get_running_count_by_session.side_effect = failure
    message = InboundMessage(channel="cli", sender_id="user", chat_id="status", content="/status")

    with pytest.raises(RuntimeError, match=f"{source} data source failed"):
        await cmd_status(
            CommandContext(
                msg=message,
                session=session,
                key=session.key,
                raw="/status",
                loop=loop,
                runtime=runtime,
            )
        )
