"""Regression tests for gateway runtime resource teardown on stop.

Covers the lifecycle contract of ``close_runtime``: runtime tasks
(including the agent loop and in-flight turns) are cancelled and awaited --
bounded -- before exec sessions, subagents, and MCP servers are closed, the
close is deterministic and idempotent, and a stuck or failing cleanup cannot
block the stop.
"""

import asyncio
import time
from contextlib import suppress
from types import SimpleNamespace

import pytest
from cirno_core.agent.hook import AgentRunHookContext
from cirno_core.agent.tools.mcp.provider import MCPProvider
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_server.lifecycle.health import channel_readiness
from cirno_server.lifecycle.mcp import MCPReadinessHook
from cirno_server.lifecycle.shutdown import close_runtime


class _FakeAgent:
    def __init__(self, events: list[str] | None = None) -> None:
        self.close_calls = 0
        self.events = events if events is not None else []
        self.hang_on_close = False
        self.raise_on_close = False
        self.background: asyncio.Task[None] | None = None

    async def aclose(self) -> None:
        self.close_calls += 1
        if self.hang_on_close:
            await asyncio.sleep(3600)
        if self.raise_on_close:
            raise RuntimeError("cleanup exploded")
        if self.background is not None:
            await self.background
        self.events.append("aclose")


class _FakeChannels:
    def __init__(self) -> None:
        self.stopped = 0
        self.events: list[str] = []

    async def stop_all(self) -> None:
        self.stopped += 1
        self.events.append("channels_stopped")


class _FakeMCPProvider:
    def __init__(self, events: list[str] | None = None) -> None:
        self.close_calls = 0
        self.events = events if events is not None else []

    async def aclose(self) -> None:
        self.close_calls += 1
        self.events.append("mcp_closed")


class _TrackingMCPProvider(MCPProvider):
    def __init__(self) -> None:
        super().__init__({}, ToolRegistry())
        self.connect_calls = 0

    async def connect(self) -> None:
        self.connect_calls += 1


def test_gateway_readiness_is_degraded_when_required_websocket_is_unavailable() -> None:
    channels = type(
        "Channels",
        (),
        {
            "enabled_channels": ["websocket"],
            "get_status": lambda self: {
                "websocket": {
                    "enabled": True,
                    "running": False,
                    "state": "starting",
                }
            },
        },
    )()

    ready, payload = channel_readiness(channels)

    assert ready is False
    assert payload == {
        "status": "degraded",
        "process": "alive",
        "ready": False,
        "websocket": "starting",
    }


def test_readiness_cannot_report_healthy_after_channel_status_failure() -> None:
    def failed_status():
        raise RuntimeError("channel status unavailable")

    channels = SimpleNamespace(enabled_channels=[], get_status=failed_status)
    ready, payload = channel_readiness(channels)

    assert ready is False
    assert payload["status"] == "degraded"


async def test_mcp_readiness_hook_delegates_to_application_provider() -> None:
    provider = _TrackingMCPProvider()
    hook = MCPReadinessHook(provider)

    await hook.before_run(AgentRunHookContext(messages=[]))

    assert provider.connect_calls == 1


async def _cancellable_task(events: list[str]) -> None:
    try:
        await asyncio.sleep(3600)
    except asyncio.CancelledError:
        events.append("cancelled")
        raise


async def _stubborn_task(events: list[str]) -> None:
    """Task that swallows cancellation and keeps running."""
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        events.append("swallowed")
        await asyncio.sleep(3600)


async def test_runtime_tasks_cancelled_before_resources_closed() -> None:
    events: list[str] = []
    agent = _FakeAgent(events)
    provider = _FakeMCPProvider(events)
    channels = _FakeChannels()
    task = asyncio.create_task(_cancellable_task(events))
    await asyncio.sleep(0)  # let the task start (cancellation pre-start skips its body)

    await close_runtime(agent, provider, channels, [task], None)

    assert events == ["cancelled", "aclose", "mcp_closed"]
    assert channels.stopped == 1
    assert agent.close_calls == 1
    assert task.cancelled()


async def test_pending_background_work_is_drained_before_close_returns() -> None:
    agent = _FakeAgent()
    provider = _FakeMCPProvider()
    channels = _FakeChannels()
    done: dict[str, bool] = {"done": False}

    async def background_work() -> None:
        await asyncio.sleep(0.01)
        done["done"] = True

    agent.background = asyncio.create_task(background_work())

    await close_runtime(agent, provider, channels, [], None)

    assert done["done"] is True
    assert agent.close_calls == 1


async def test_stubborn_task_does_not_block_past_wait_timeout() -> None:
    agent = _FakeAgent()
    provider = _FakeMCPProvider()
    channels = _FakeChannels()
    events: list[str] = []
    task = asyncio.create_task(_stubborn_task(events))
    await asyncio.sleep(0)  # let the task start (cancellation pre-start skips its body)
    runtime_tasks = asyncio.gather(task)

    start = time.monotonic()
    await close_runtime(
        agent,
        provider,
        channels,
        [task],
        runtime_tasks,
        task_wait_timeout=0.05,
    )
    elapsed = time.monotonic() - start
    for _ in range(10):
        await asyncio.sleep(0)  # let the swallowed cancellation handler run

    assert "swallowed" in events  # task was cancelled, then refused to die
    assert task.done()  # the timed-out task received a second cancellation
    assert runtime_tasks.done()
    assert agent.close_calls == 1  # resources still closed underneath it
    assert provider.close_calls == 1
    assert elapsed < 1.0  # bounded, not held open by the stubborn task


async def test_hanging_close_is_bounded_and_reported() -> None:
    agent = _FakeAgent()
    provider = _FakeMCPProvider()
    agent.hang_on_close = True
    channels = _FakeChannels()

    start = time.monotonic()
    with pytest.raises(ExceptionGroup) as failure:
        await close_runtime(
            agent,
            provider,
            channels,
            [],
            None,
            close_timeout=0.05,
        )
    assert isinstance(failure.value.exceptions[0], TimeoutError)
    elapsed = time.monotonic() - start

    assert agent.close_calls == 1
    assert provider.close_calls == 1
    assert channels.stopped == 1
    assert elapsed < 1.0


async def test_failing_close_is_reported_after_remaining_resources_close() -> None:
    agent = _FakeAgent()
    provider = _FakeMCPProvider()
    agent.raise_on_close = True
    channels = _FakeChannels()

    with pytest.raises(ExceptionGroup) as failure:
        await close_runtime(agent, provider, channels, [], None)
    assert str(failure.value.exceptions[0]) == "cleanup exploded"

    assert agent.close_calls == 1
    assert provider.close_calls == 1
    assert channels.stopped == 1  # teardown continued past the failure


async def test_duplicate_cleanup_is_idempotent() -> None:
    agent = _FakeAgent()
    provider = _FakeMCPProvider()
    channels = _FakeChannels()
    task = asyncio.create_task(_cancellable_task([]))

    await close_runtime(agent, provider, channels, [task], None)
    await close_runtime(agent, provider, channels, [task], None)

    assert agent.close_calls == 2  # second pass is a clean no-op
    assert provider.close_calls == 2
    assert channels.stopped == 2
    assert task.cancelled()


async def test_finished_runtime_tasks_gather_is_retrieved() -> None:
    agent = _FakeAgent()
    provider = _FakeMCPProvider()
    channels = _FakeChannels()
    finished = asyncio.get_running_loop().create_future()
    finished.set_result(None)
    runtime_tasks = asyncio.gather(finished)
    await asyncio.sleep(0)  # let the gather observe the finished child

    await close_runtime(agent, provider, channels, [], runtime_tasks)

    assert runtime_tasks.done()
    assert agent.close_calls == 1
    assert provider.close_calls == 1


async def test_cancelled_runtime_tasks_gather_does_not_raise() -> None:
    agent = _FakeAgent()
    provider = _FakeMCPProvider()
    channels = _FakeChannels()
    runtime_tasks = asyncio.gather(asyncio.sleep(3600))
    runtime_tasks.cancel()

    await close_runtime(agent, provider, channels, [], runtime_tasks)
    with suppress(asyncio.CancelledError):
        await runtime_tasks  # settle the cancelled gather without raising

    assert runtime_tasks.done()  # the cancelled gather was awaited without raising
    assert agent.close_calls == 1
    assert provider.close_calls == 1


async def test_channel_shutdown_failure_still_closes_runtime_resources() -> None:
    class FailedChannels(_FakeChannels):
        async def stop_all(self) -> None:
            raise RuntimeError("channel transport failed to close")

    events: list[str] = []
    agent, provider = _FakeAgent(events), _FakeMCPProvider(events)
    task = asyncio.create_task(_cancellable_task(events))
    await asyncio.sleep(0)
    with pytest.raises(BaseExceptionGroup) as failure:
        await close_runtime(agent, provider, FailedChannels(), [task], None)
    assert task.cancelled()
    assert events == ["cancelled", "aclose", "mcp_closed"]
    assert "channel transport failed to close" in str(failure.value.exceptions[0])


async def test_hanging_channel_stop_is_bounded_and_resources_still_close() -> None:
    class HangingChannels(_FakeChannels):
        async def stop_all(self) -> None:
            await asyncio.sleep(3600)

    agent, provider = _FakeAgent(), _FakeMCPProvider()
    with pytest.raises(ExceptionGroup) as failure:
        await close_runtime(agent, provider, HangingChannels(), [], None, close_timeout=0.05)
    assert isinstance(failure.value.exceptions[0], TimeoutError)
    assert agent.close_calls == provider.close_calls == 1


async def test_failed_runtime_gather_is_reported_after_cleanup() -> None:
    async def failed_runner() -> None:
        raise RuntimeError("dispatch runner failed")

    agent, provider = _FakeAgent(), _FakeMCPProvider()
    task = asyncio.create_task(failed_runner())
    gathered = asyncio.gather(task)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    with pytest.raises(ExceptionGroup) as failure:
        await close_runtime(agent, provider, _FakeChannels(), [task], gathered)
    assert str(failure.value.exceptions[0]) == "dispatch runner failed"
    assert agent.close_calls == provider.close_calls == 1
