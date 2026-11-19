"""Rejected automation inputs must settle their waiting scheduler or trigger."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.agent.automation_turns import AutomationTurnError
from cirno_core.bus.events import InboundMessage
from cirno_core.cron.session_turns import CRON_TRIGGER_META
from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY
from cirno_core.session.recovery.pending import pending_followups
from cirno_core.triggers.local_session_turns import LOCAL_TRIGGER_META


@pytest.mark.parametrize("kind", ["cron", "trigger"])
@pytest.mark.parametrize("rejected_at", ["recovery", "goal"])
async def test_rejected_automation_settles_its_submitter(loop_factory, monkeypatch, kind, rejected_at):
    loop = loop_factory()
    loop.provider.aclose = AsyncMock()
    entered = asyncio.Event()

    async def reject(*_args):
        entered.set()
        return False

    if rejected_at == "recovery":
        loop.recovery_admission = SimpleNamespace(
            admit=reject, register_recovery_task=MagicMock(), unregister_recovery_task=MagicMock(),
        )
    else:
        monkeypatch.setattr(loop.dispatch.turn, "current_goal", reject)
    process = AsyncMock()
    monkeypatch.setattr(loop.processing, "process", process)
    metadata = (
        {CRON_TRIGGER_META: {"run_id": "run", "job_id": "job"}}
        if kind == "cron" else {LOCAL_TRIGGER_META: {"delivery_id": "run", "trigger_id": "job"}}
    )
    message = InboundMessage("websocket", kind, "rejected", "Obsolete input", metadata=metadata)
    submit = loop.submit_cron_turn if kind == "cron" else loop.submit_local_trigger_turn
    waiting = asyncio.create_task(submit(message))
    try:
        async with asyncio.timeout(2):
            await entered.wait()
            await asyncio.gather(*tuple(loop._active_tasks.get(message.session_key, ())))
            await asyncio.sleep(0)
            assert waiting.done(), "A rejected automation left its submitter waiting forever"
            with pytest.raises(AutomationTurnError, match=rejected_at):
                await waiting
        process.assert_not_awaited()
        assert not loop.pending_cron_job_ids_for_session(message.session_key)
        assert not loop.pending_local_trigger_ids_for_session(message.session_key)
    finally:
        waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)
        loop.recovery_admission = None
        await loop.aclose()


@pytest.mark.parametrize("continuation", [False, True])
async def test_stale_goal_guard_does_not_create_a_missing_session(loop_factory, continuation):
    loop = loop_factory()
    loop.provider.aclose = AsyncMock()
    metadata = {"_goal_id": "obsolete"}
    if continuation:
        metadata.update(_internal_continuation=True, _internal_continuation_kind="sustained_goal")
    message = InboundMessage("websocket", "system:continuation", "removed", "Old continuation", metadata=metadata)
    try:
        assert not await loop.dispatch.turn.current_goal(message, message.session_key)
        assert await loop.sessions.state.read_header(message.session_key) is None
    finally:
        await loop.aclose()


@pytest.mark.parametrize("guard", ["goal", "continuation", "approval"])
async def test_goal_guard_rejects_discarded_history_even_with_same_goal_id(loop_factory, monkeypatch, guard):
    loop = loop_factory()
    loop.provider.aclose = AsyncMock()
    key = "websocket:replaced"
    original = await loop.sessions.state.get_header(key)
    await loop.sessions.state.reset(key)
    replacement = await loop.sessions.state.get_header(key)
    assert replacement.generation != original.generation
    await loop.sessions.state.update_metadata(key, {
        "goal_state": {"goal_id": "same", "status": "active", "objective": "Current work"},
    })
    metadata = {"_goal_id": "same"}
    if guard == "continuation":
        metadata.update(_internal_continuation=True, _internal_continuation_kind="sustained_goal")
    elif guard == "approval":
        metadata.update(_approval_decision=True, **{PENDING_FOLLOWUP_ID_KEY: "old"})
    acknowledge = AsyncMock()
    monkeypatch.setattr(loop.sessions.state, "acknowledge_followups", acknowledge)
    message = InboundMessage("websocket", "system:continuation", "replaced", "Old input",
                             metadata=metadata, session_generation=original.generation)
    try:
        assert not await loop.dispatch.turn.current_goal(message, key)
        acknowledge.assert_not_awaited()
        message.session_generation = replacement.generation
        assert await loop.dispatch.turn.current_goal(message, key)
    finally:
        await loop.aclose()


@pytest.mark.parametrize("guard", ["goal", "recovery"])
async def test_rejected_approval_cannot_acknowledge_a_replacement_history(loop_factory, monkeypatch, guard):
    loop = loop_factory()
    loop.provider.aclose = AsyncMock()
    key = "websocket:approval-reset"
    original = await loop.sessions.state.get_header(key)
    await loop.sessions.state.update_metadata(key, {
        "goal_state": {"goal_id": "same", "status": "stopped", "objective": "Old work"},
    })
    acknowledge = loop.sessions.state.acknowledge_followups

    async def replaced_before_ack(*args, **kwargs):
        await loop.sessions.state.reset(key)
        await loop.sessions.state.queue_followup(key, InboundMessage(
            "websocket", "owner", "approval-reset", "Retained new request",
            metadata={PENDING_FOLLOWUP_ID_KEY: "restored-id"},
        ))
        await acknowledge(*args, **kwargs)

    monkeypatch.setattr(loop.sessions.state, "acknowledge_followups", replaced_before_ack)
    message = InboundMessage(
        "websocket", "system:approval", "approval-reset", "Old approval",
        metadata={"_approval_decision": True, "_goal_id": "same", PENDING_FOLLOWUP_ID_KEY: "restored-id"},
        session_generation=original.generation,
    )
    try:
        if guard == "goal":
            assert not await loop.dispatch.turn.current_goal(message, key)
        else:
            from cirno_core.session.recovery.coordinator import RecoveryCoordinator

            assert not await RecoveryCoordinator(loop.sessions, loop.bus).admit(message)
        current = await loop.sessions.state.read(key)
        assert [item.content for item in pending_followups(current)] == ["Retained new request"]
    finally:
        await loop.aclose()
