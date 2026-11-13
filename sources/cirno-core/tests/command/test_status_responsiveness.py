"""Large status measurements yield the loop and preserve request ownership."""

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from cirno_core.agent.tools.context import RequestContext, current_request_context, request_context
from cirno_core.bus.events import InboundMessage
from cirno_core.command.builtin.service import cmd_status
from cirno_core.command.router import CommandContext
from cirno_core.security.workspace_access import WorkspaceScopeResolver, current_workspace_scope
from cirno_core.session.model import Session


async def test_status_measurement_yields_and_binds_the_target_context(tmp_path, monkeypatch):
    session = Session(key="websocket:measured-worker")
    session.messages = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": "科研 evidence " * 100}
        for index in range(2000)
    ]
    entered = threading.Event()
    release = threading.Event()
    observed = []
    main_thread = threading.get_ident()
    loop = MagicMock()
    loop._active_tasks = {}
    loop._start_time = time.time()
    loop.subagents.get_running_count_by_session.return_value = 0
    loop.workspace_scopes = WorkspaceScopeResolver(
        default_workspace=tmp_path,
        default_restrict_to_workspace=False,
    )
    runtime = SimpleNamespace(
        model="test-model",
        context_window_tokens=512_000,
        generation=SimpleNamespace(max_tokens=100),
        output_reserve_percent=5, active_compact_percent=100,
    )

    def estimate(*_args, **_kwargs):
        observed.append(
            (threading.get_ident(), current_request_context(), current_workspace_scope())
        )
        entered.set()
        if not release.wait(timeout=2):
            raise TimeoutError("status measurement blocked the event loop")
        return 300_000, "test"

    loop.consolidator.estimate_session_prompt_tokens.side_effect = estimate
    monkeypatch.setattr(
        "cirno_core.command.builtin.service.fetch_search_usage",
        AsyncMock(return_value=SimpleNamespace(format=lambda: "search usage")),
    )
    original_history = session.get_history
    history_threads = []

    def history(**kwargs):
        history_threads.append(threading.get_ident())
        return original_history(**kwargs)

    monkeypatch.setattr(session, "get_history", history)
    message = InboundMessage(
        channel="websocket", sender_id="owner", chat_id="measured-worker", content="/status"
    )
    parent = RequestContext(channel="websocket", chat_id="other", session_key="websocket:other")
    with request_context(parent):
        task = asyncio.create_task(
            cmd_status(
                CommandContext(
                    msg=message,
                    session=session,
                    key=session.key,
                    raw="/status",
                    loop=loop,
                    runtime=runtime,
                )
            )
        )
        try:
            assert await asyncio.wait_for(asyncio.to_thread(entered.wait, 1), timeout=1.5)
            assert not task.done(), "status must yield while its physical measurement is unfinished"
            assert current_request_context() is parent
        finally:
            release.set()
            responses = await asyncio.gather(task, return_exceptions=True)
        response = responses[0]
        assert not isinstance(response, BaseException), repr(response)
        assert "Context: 300k/512k" in response.content
        assert "Session: 2000 messages" in response.content
        assert current_request_context() is parent
    assert observed[0][0] != main_thread
    assert observed[0][1].session_key == session.key
    assert observed[0][1].runtime is runtime
    assert observed[0][2].project_path == tmp_path
    assert history_threads and main_thread not in history_threads
    assert current_request_context() is None
    assert current_workspace_scope() is None
