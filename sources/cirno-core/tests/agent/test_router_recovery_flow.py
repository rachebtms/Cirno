"""Router supervision stays live at capacity and resumes committed work once."""

import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock

from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.tools.context import current_request_context
from cirno_core.agent.turn_delivery import TurnDeliveryFactory
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.generation import GenerationSettings
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.contracts import RECOVERY_METADATA_KEY
from cirno_core.session.recovery.coordinator import RecoveryCoordinator
from cirno_core.session.router_session import ensure_router_session
from cirno_core.session.session_handles import SessionHandleResolver
from cirno_core.session.webui_turns.coordinator import WebuiTurnCoordinator
from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy

WORKER = "websocket:2bfcd651-4ef4-4401-83cc-0ac33cc3afc8"
HEALTHY = "websocket:fdf1f189-4b9f-43a6-9933-c38977a85b27"


class RecoveryProvider(LLMProvider):
    def __init__(self, artifact):
        super().__init__(provider_name="recovery-fixture")
        self.generation = GenerationSettings(max_tokens=1024)
        self.retry_policy.delays = ()
        self.artifact = artifact
        self.worker_requests = []
        self.router_calls = {"failed": 0, "ready": 0}
        self.worker_failed = asyncio.Event()
        self.healthy_entered = asyncio.Event()
        self.release_healthy = asyncio.Event()
        self.continued = asyncio.Event()
        self.finished = asyncio.Event()
        self.closed = False

    def get_default_model(self):
        return "fixture"

    async def aclose(self):
        self.closed = True

    async def chat(self, messages, tools=None, **kwargs):
        context = current_request_context()
        assert context is not None
        if context.session_key == HEALTHY:
            self.healthy_entered.set()
            await self.release_healthy.wait()
            return LLMResponse(content="Independent task complete")
        if context.session_key == WORKER:
            self.worker_requests.append(deepcopy(messages))
            if len(self.worker_requests) == 1:
                return self.call(
                    "write-once",
                    "files__write",
                    path=str(self.artifact),
                    content="Verified side effect",
                )
            if len(self.worker_requests) == 2:
                self.worker_failed.set()
                return LLMResponse(
                    content="Fixture API unavailable",
                    finish_reason="error",
                    error_kind="connection",
                )
            assert len(self.worker_requests) == 3
            assert any(
                message.get("role") == "tool" and "Successfully" in str(message.get("content"))
                for message in messages
            )
            return LLMResponse(content="Recovered using the saved tool result")

        assert context.session_key == ROUTER_SESSION_KEY
        state = context.metadata["_work_report"]["state"]
        self.router_calls[state] += 1
        call = self.router_calls[state]
        if state == "failed":
            if call == 1:
                await self.healthy_entered.wait()
                while self.loop.dispatch.is_running(WORKER):
                    await asyncio.sleep(0)
                assert "model_request_failed" in str(messages) or "connection" in str(messages)
                return self.call("list-execution", "conversations__control", action="list")
            if call == 2:
                status = json.loads(messages[-1]["content"])
                assert (
                    status["worker_concurrency_limit"] == 1 and status["router_has_reserved_slot"]
                )
                rows = {row["session_key"]: row for row in status["conversations"]}
                assert rows[HEALTHY]["execution_status"] == "running"
                assert rows[WORKER]["execution_status"] == "interrupted"
                return self.call(
                    "continue-worker",
                    "conversations__control",
                    action="continue",
                    to=self.worker_id,
                )
            if call == 3:
                result = json.loads(messages[-1]["content"])
                assert result["continuation_queued"] is True
                self.continued.set()
                return self.call(
                    "recovery-notice", "user__message", content="Recovering the interrupted worker"
                )
            return LLMResponse(content="")
        assert state == "ready"
        if call == 1:
            assert "Recovered using the saved tool result" in str(messages)
            return self.call(
                "result-notice",
                "user__message",
                content="Recovery complete; the file was written once",
            )
        self.finished.set()
        return LLMResponse(content="")

    @staticmethod
    def call(identifier, name, **arguments):
        return LLMResponse(content=None, tool_calls=[ToolCallRequest(identifier, name, arguments)])


async def test_failure_report_drives_router_continue_while_worker_capacity_is_full(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CIRNO_MAX_CONCURRENT_REQUESTS", "1")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sessions = SessionManager(workspace, sessions_root=tmp_path / "sessions")
    await ensure_router_session(sessions)
    for key in (WORKER, HEALTHY):
        await sessions.state.get_header(key)
        await sessions.state.update_metadata(
            key, {"webui": True, "title": "Fixture", "title_user_edited": True}
        )
    await sessions.state.update_metadata(WORKER, {"delegated_by": ROUTER_SESSION_KEY})
    bus = MessageBus()
    provider = RecoveryProvider(workspace / "evidence.txt")
    recovery = RecoveryCoordinator(sessions, bus)
    route = WebuiTurnRoutePolicy(sessions)
    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=workspace,
        session_manager=sessions,
        recovery_admission=recovery,
        turn_delivery_factory=TurnDeliveryFactory(bus, route, route.admit),
    )
    provider.loop = loop
    provider.worker_id = (await SessionHandleResolver(sessions).ahandle_for_session(WORKER)).id
    tool = loop.tools.get("write_file")
    write = AsyncMock(wraps=tool.execute)
    monkeypatch.setattr(tool, "execute", write)
    coordinator = WebuiTurnCoordinator(bus, sessions, loop.schedule_background, recovery=recovery)
    runner = None
    try:
        with coordinator.connected():
            runner = asyncio.create_task(loop.run())
            async with asyncio.timeout(15):
                for key in (WORKER, HEALTHY):
                    await bus.publish_inbound(
                        InboundMessage(
                            channel="websocket",
                            sender_id="user",
                            chat_id=key.split(":", 1)[1],
                            content="Complete the authorized task",
                            require_existing_session=True,
                            metadata={"webui": True, "webui_turn_id": key + ":request"},
                        )
                    )
                    if key == WORKER:
                        await provider.worker_failed.wait()
                await provider.continued.wait()
                header = await sessions.state.read_header(WORKER)
                assert header.metadata[RECOVERY_METADATA_KEY]["status"] == "resuming"
                assert provider.artifact.read_text() == "Verified side effect"
                provider.release_healthy.set()
                await provider.finished.wait()
                while loop._pending_queues or bus.inbound_size:
                    await asyncio.sleep(0)
            final = await sessions.state.get(WORKER)
            assert final.metadata[RECOVERY_METADATA_KEY]["status"] == "recovered"
            assert sum(message.get("role") == "user" for message in final.messages) == 1
            write.assert_awaited_once()
            assert len(provider.worker_requests) == 3
            visible = []
            while bus.outbound_size:
                message = await bus.consume_outbound()
                if message.chat_id == ROUTER_SESSION_KEY.split(":", 1)[1] and message.content:
                    visible.append(message.content)
            assert visible == [
                "Recovering the interrupted worker",
                "Recovery complete; the file was written once",
            ]
    finally:
        provider.release_healthy.set()
        loop.stop()
        if runner is not None:
            runner.cancel()
            try:
                await runner
            except asyncio.CancelledError:
                pass
        else:
            await loop.aclose()
    assert provider.closed
