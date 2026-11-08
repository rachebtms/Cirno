"""Accepted inputs always settle, including failures before the model pipeline."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.bus.events import InboundMessage, OutboundMessage
from cirno_core.bus.outbound_events import TurnEndEvent
from cirno_core.bus.runtime_events import TurnCompleted
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.recovery.contracts import RECOVERY_INBOUND_METADATA_KEY
from cirno_core.session.webui_turns.coordinator import WebuiTurnCoordinator

from sources.development.testing.sessions import run_session


@pytest.mark.parametrize("failure_at", ["recovery", "lock", "gate", "goal", "route"])
async def test_setup_failure_finishes_its_turn_reports_to_router_and_keeps_fifo(loop_factory, monkeypatch, failure_at):
    loop = loop_factory()
    loop.provider.aclose = AsyncMock()
    worker = await loop.sessions.state.get("websocket:worker")
    await loop.sessions.state.update_metadata(worker.key, {"delegated_by": ROUTER_SESSION_KEY, "webui": True})
    await loop.sessions.state.get(ROUTER_SESSION_KEY)
    wire = WebuiTurnCoordinator(loop.bus, loop.sessions, loop.schedule_background)
    unsubscribe = wire.subscribe()
    completed = []
    loop.bus.subscribe(completed.append, TurnCompleted)
    problem = OSError(f"Injected {failure_at} failure")
    process = AsyncMock(return_value=OutboundMessage("websocket", "worker", "next input completed"))
    monkeypatch.setattr(loop.processing, "process", process)
    coordinator = SimpleNamespace(complete=MagicMock(), defer_if_active=MagicMock(return_value=False), owns_turn=MagicMock(return_value=False))
    loop._automation_turn_coordinators = [coordinator]
    metadata = {"webui_turn_id": "failed-input", "webui": True}
    if failure_at == "recovery":
        loop.recovery_admission = SimpleNamespace(
            admit=AsyncMock(side_effect=[problem, True]),
            register_recovery_task=MagicMock(), unregister_recovery_task=MagicMock(),
        )
        metadata[RECOVERY_INBOUND_METADATA_KEY] = "recovery-id"
    elif failure_at == "lock":
        real_lock = loop._get_session_lock
        monkeypatch.setattr(loop, "_get_session_lock", MagicMock(side_effect=[problem, real_lock(worker.key)]))
    elif failure_at == "gate":
        class Gate:
            entered = False
            async def __aenter__(self):
                if not self.entered:
                    self.entered = True
                    raise problem
            async def __aexit__(self, *args):
                return False
        loop._concurrency_gate = Gate()
    elif failure_at == "goal":
        metadata["_goal_id"] = "goal-id"
        monkeypatch.setattr(loop.sessions.state, "get_header", AsyncMock(side_effect=problem))
    else:
        create = loop.turn_delivery_factory.create
        async def create_once(*args, **kwargs):
            if not getattr(create_once, "failed", False):
                create_once.failed = True
                raise problem
            return await create(*args, **kwargs)
        monkeypatch.setattr(loop.turn_delivery_factory, "create", create_once)
    msg = InboundMessage("websocket", "owner", "worker", "first", metadata=metadata, session_generation=worker.generation)
    try:
        await run_session(loop, msg)
        failed = [event for event in completed if event.context.metadata.get("webui_turn_id") == "failed-input"]
        assert len(failed) == 1 and failed[0].outcome == "failed"
        wire_end = [item for item in loop.bus.outbound._queue if isinstance(item.event, TurnEndEvent)
                    and item.metadata.get("webui_turn_id") == "failed-input"]
        assert len(wire_end) == 1 and wire_end[0].event.outcome == "failed"
        report = (await loop.sessions.state.read_metadata(worker.key))["metadata"]["work_report"]
        assert report["state"] == "failed" and report["execution"]["stage"] != "run"
        assert problem.args[0] in report["summary"]
        coordinator.complete.assert_called_with(msg, error=problem)
        if failure_at == "recovery":
            loop.recovery_admission.unregister_recovery_task.assert_called_once()
        await run_session(loop, InboundMessage("websocket", "owner", "worker", "second", metadata={"webui_turn_id": "next-input"}))
        assert process.await_count == 1
        assert any(event.context.metadata.get("webui_turn_id") == "next-input" and event.outcome == "completed" for event in completed)
        assert not loop._executing_sessions and not loop._pending_queues
    finally:
        unsubscribe()
        await loop.aclose()


async def test_intake_error_settles_input_without_shutting_down_other_conversations(loop_factory, monkeypatch):
    loop = loop_factory()
    loop.provider.aclose = AsyncMock()
    completed = []
    failed, healthy = asyncio.Event(), asyncio.Event()
    def observe(event):
        completed.append(event)
        (failed if event.context.chat_id == "rejected" else healthy).set()
    loop.bus.subscribe(observe, TurnCompleted)
    receive = loop.dispatch.receive
    async def reject_once(message):
        if message.chat_id == "rejected":
            raise OSError("Injected admission storage error")
        await receive(message)
    monkeypatch.setattr(loop.dispatch, "receive", reject_once)
    process = AsyncMock(return_value=OutboundMessage("websocket", "healthy", "still running"))
    monkeypatch.setattr(loop.processing, "process", process)
    worker = asyncio.create_task(loop.run())
    try:
        await loop.bus.publish_inbound(InboundMessage("websocket", "owner", "rejected", "first"))
        await asyncio.wait_for(failed.wait(), 3)
        assert not worker.done()
        await loop.bus.publish_inbound(InboundMessage("websocket", "owner", "healthy", "second"))
        await asyncio.wait_for(healthy.wait(), 3)
        assert [(event.context.chat_id, event.outcome) for event in completed] == [("rejected", "failed"), ("healthy", "completed")]
        process.assert_awaited_once()
    finally:
        loop.stop()
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await loop.aclose()


async def test_archive_release_error_uses_processing_failure_stage_exactly_once(loop_factory, monkeypatch):
    loop = loop_factory()
    loop.provider.aclose = AsyncMock()
    session = await loop.sessions.state.get("websocket:delegated")
    await loop.sessions.state.update_metadata(session.key, {"delegated_by": ROUTER_SESSION_KEY})
    monkeypatch.setattr(loop.persistence, "release_archive", AsyncMock(side_effect=OSError("Archive store unavailable")))
    record = AsyncMock(wraps=loop.reports.record)
    monkeypatch.setattr(loop.reports, "record", record)
    completed = []
    loop.bus.subscribe(completed.append, TurnCompleted)
    try:
        await run_session(loop, InboundMessage("websocket", "owner", "delegated", "continue research", session_generation=session.generation))
        assert len(completed) == 1 and completed[0].outcome == "failed"
        assert record.await_count == 1
        report = (await loop.sessions.state.read_metadata(session.key))["metadata"]["work_report"]
        assert report["execution"]["stage"] == "restore"
        assert "Archive store unavailable" in report["summary"]
    finally:
        await loop.aclose()


async def test_deferred_reporting_diagnostics_keep_private_input_out_of_tracebacks(loop_factory, monkeypatch):
    from cirno_core.agent.execution.context import TurnContext, TurnKind
    from cirno_core.session.model import SessionPolicy
    from loguru import logger
    loop = loop_factory()
    loop.provider.aclose = AsyncMock()
    key = "websocket:private"
    await loop.sessions.state.get(key)
    await loop.sessions.state.set_policy(key, SessionPolicy(log_content=False))
    marker = "synthetic-private-input-and-diagnostic"
    msg = InboundMessage("websocket", "owner", "private", marker)
    ctx = TurnContext(msg=msg, session_key=key, turn_id="private-failure", runtime=None,
                      kind=TurnKind.USER, delivery=loop.turn_delivery_factory.unrouted(msg, key))
    monkeypatch.setattr(loop.reports, "record", AsyncMock(side_effect=OSError(marker)))
    records = []
    sink = logger.add(lambda message: records.append(message.record))
    try:
        await loop.reports.publish(ctx, stage="restore", error=OSError(marker))
        failures = [record for record in records if "reporting deferred" in record["message"]]
        assert len(failures) == 1 and failures[0]["exception"] is None
        assert marker not in failures[0]["message"]
    finally:
        logger.remove(sink)
        await loop.aclose()
