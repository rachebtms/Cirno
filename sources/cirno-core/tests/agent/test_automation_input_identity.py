"""Automation invocations must not replay their creating coordination input."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.bus.events import InboundMessage, OutboundMessage
from cirno_core.cron.bound_runner import run_bound_cron_job
from cirno_core.cron.session_turns import cron_run_id
from cirno_core.cron.types import CronJob, CronPayload
from cirno_core.session.session_messages import SESSION_MESSAGE_METADATA_KEY
from cirno_core.triggers.local_runner import _deliver_delivery
from cirno_core.triggers.local_session_turns import local_trigger_delivery_id
from cirno_core.triggers.local_store import LocalTriggerStore


@pytest.mark.parametrize("source", ["cron", "trigger"])
async def test_legacy_automation_dispatch_does_not_reuse_a_consumed_input(loop_factory, monkeypatch, tmp_path, source):
    loop = loop_factory()
    loop.provider.aclose = AsyncMock()
    key, chat = "websocket:reminder", "reminder"
    origin = {
        SESSION_MESSAGE_METADATA_KEY: {
            "message_id": "creating-message", "created_at_ms": 1, "expect_reply": False,
            "source_handle": "cirno", "source_session_key": "websocket:router",
            "target_session_key": key,
        },
        "_work_report": {"state": "ready"},
        "_hidden_history": {"kind": "work_report"},
        "message_thread_id": 42,
    }
    snapshot = deepcopy(origin)
    creating = InboundMessage("websocket", "sender", chat, "Create the nightly reminder", metadata=origin)
    processed = AsyncMock(return_value=OutboundMessage("websocket", chat, "Done"))
    monkeypatch.setattr(loop.processing, "process", processed)
    try:
        journal = await loop.sessions.state.queue_followup(key, creating)
        assert journal is not None
        await loop.sessions.state.acknowledge_followups(key, [journal])
        # Bypass save-time normalization: existing installations may already
        # contain an origin snapshot with a consumed message's identity.
        if source == "cron":
            job = CronJob(id="saved", name="Reminder", payload=CronPayload(
                message="Check progress", session_key=key, origin_channel="websocket",
                origin_chat_id=chat, origin_metadata=origin,
            ))
        else:
            store = LocalTriggerStore(tmp_path / "triggers")
            trigger = store.create(name="Reminder", channel="websocket", chat_id=chat, session_key=key)
            trigger.origin_metadata = origin
            store._save_triggers_unlocked([trigger])
        async with asyncio.timeout(3):
            for _ in range(2):
                if source == "cron":
                    await run_bound_cron_job(job, agent=loop, cron=MagicMock())
                else:
                    store.enqueue(trigger.id, "Check progress")
                    [delivery] = store.claim_deliveries()
                    await _deliver_delivery(
                        store, delivery, submit_turn=loop.submit_local_trigger_turn,
                        is_channel_enabled=lambda _: True,
                    )
                    store.complete_delivery(delivery)
        assert processed.await_count == 2
        messages = [call.args[0] for call in processed.await_args_list]
        identity = cron_run_id if source == "cron" else local_trigger_delivery_id
        ids = [identity(message.metadata) for message in messages]
        assert all(ids) and ids[0] != ids[1]
        for message in messages:
            assert message.session_key == key
            assert message.metadata["message_thread_id"] == 42
            assert SESSION_MESSAGE_METADATA_KEY not in message.metadata
            assert "_work_report" not in message.metadata
            assert "_hidden_history" not in message.metadata
        assert origin == snapshot
        # Keep the original input's receipt authoritative: genuine redelivery
        # is still suppressed, rather than resetting or bypassing deduplication.
        assert await loop.sessions.state.queue_followup(key, creating) is None
    finally:
        await loop.aclose()
