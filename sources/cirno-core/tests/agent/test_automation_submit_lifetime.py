"""Cancelled deferred submissions do not survive as a second accepted turn."""

import asyncio

import pytest
from cirno_core.agent.cron_turns import CronTurnCoordinator
from cirno_core.bus.events import InboundMessage, OutboundMessage
from cirno_core.cron.session_turns import CRON_DEFER_UNTIL_IDLE_META, CRON_TRIGGER_META
from cirno_core.triggers.local_session_turns import LOCAL_TRIGGER_META
from cirno_core.triggers.local_turns import LocalTriggerTurnCoordinator


@pytest.mark.parametrize("kind", ["cron", "trigger"])
async def test_cancelled_deferred_submit_is_removed_without_losing_other_automation_kinds(kind):
    key = "websocket:busy"
    cron_meta = {
        CRON_TRIGGER_META: {"run_id": "run", "job_id": "job"},
        CRON_DEFER_UNTIL_IDLE_META: True,
    }
    trigger_meta = {LOCAL_TRIGGER_META: {"delivery_id": "run", "trigger_id": "job"}}
    own_meta, other_meta = (
        (cron_meta, trigger_meta) if kind == "cron" else (trigger_meta, cron_meta)
    )
    other = InboundMessage(
        "websocket", "automation", "busy", "Other accepted work", metadata=other_meta
    )
    queues = {key: [other]}
    entered = asyncio.Event()

    async def enqueue(msg):
        assert coordinator.defer_if_active(msg, session_key=key, active_session_keys=[key])
        entered.set()

    cls = CronTurnCoordinator if kind == "cron" else LocalTriggerTurnCoordinator
    coordinator = cls(enqueue=enqueue, deferred_queues=queues)
    msg = InboundMessage("websocket", "automation", "busy", "Accepted work", metadata=own_meta)
    task = asyncio.create_task(coordinator.submit(msg))
    retry = None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert queues[key] == [other]
        assert coordinator.pending_ids_for_session(key) == set()
        entered.clear()
        retry = asyncio.create_task(coordinator.submit(msg))
        await asyncio.wait_for(entered.wait(), 1)
        assert queues[key] == [other, msg]
        response = OutboundMessage("websocket", "busy", "Finished once")
        coordinator.complete(msg, response=response)
        assert await retry == response
    finally:
        task.cancel()
        if retry:
            retry.cancel()
        await asyncio.gather(task, *([retry] if retry else []), return_exceptions=True)
