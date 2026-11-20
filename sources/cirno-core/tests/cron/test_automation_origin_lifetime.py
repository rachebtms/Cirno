"""Saved automation addresses must not reuse a creating turn's lifetime."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.cron import CronTool
from cirno_core.agent.turn_delivery import TurnDeliveryFactory
from cirno_core.bus.delivery import DELIVERY_RUN_META
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.cron.bound_runner import run_bound_cron_job
from cirno_core.cron.service import CronService
from cirno_core.cron.types import CronJob, CronPayload
from cirno_core.security.workspace_access import WORKSPACE_SCOPE_METADATA_KEY, WorkspaceScopeResolver
from cirno_core.session.display_history import HISTORY_GENERATION_METADATA_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.contracts import RECOVERY_INBOUND_METADATA_KEY
from cirno_core.session.session_messages import SESSION_MESSAGE_METADATA_KEY
from cirno_core.session.transcript import WebUITranscriptRecorder
from cirno_core.session.transport_metadata import WEBSOCKET_TURN_OWNER_METADATA_KEY, WEBUI_TURN_METADATA_KEY
from cirno_core.session.turn_continuation import INTERNAL_CONTINUATION_META, SKIP_USER_PERSIST_META
from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy
from cirno_core.triggers.local_runner import _deliver_delivery
from cirno_core.triggers.local_store import LocalTriggerStore


def _creating_turn(generation, project):
    return {
        HISTORY_GENERATION_METADATA_KEY: generation,
        WEBUI_TURN_METADATA_KEY: "creating-turn",
        WEBSOCKET_TURN_OWNER_METADATA_KEY: "creating-owner",
        INTERNAL_CONTINUATION_META: True,
        SKIP_USER_PERSIST_META: True,
        RECOVERY_INBOUND_METADATA_KEY: "old-recovery",
        DELIVERY_RUN_META: "creating-delivery",
        WORKSPACE_SCOPE_METADATA_KEY: {"project_path": str(project), "access_mode": "full"},
        SESSION_MESSAGE_METADATA_KEY: {
            "message_id": "creating-message", "created_at_ms": 1, "expect_reply": False,
            "source_handle": "cirno", "source_session_key": "websocket:router",
            "target_session_key": "websocket:reminder",
        },
        "_work_report": {"state": "ready"},
        "_hidden_history": {"kind": "work_report"},
        "message_thread_id": 42,
    }


@pytest.mark.parametrize("source", ["cron", "trigger"])
async def test_old_automation_payload_gets_the_current_history_lifetime(tmp_path, source):
    sessions = SessionManager(tmp_path / "sessions")
    key, chat = "websocket:reminder", "reminder"
    header = await sessions.state.get_header(key)
    origin = _creating_turn(header.generation, tmp_path)
    await sessions.state.reset(key)
    await sessions.state.update_metadata(key, {
        WORKSPACE_SCOPE_METADATA_KEY: {"project_path": str(tmp_path), "access_mode": "restricted"},
    })
    replacement = await sessions.state.get_header(key)
    bus = MessageBus()
    policy = WebuiTurnRoutePolicy(sessions)
    factory = TurnDeliveryFactory(bus, route_policy=policy, route_admission=policy.admit)
    recorder = WebUITranscriptRecorder(sessions)
    seen = []

    async def submit(message):
        assert not message.metadata.get(INTERNAL_CONTINUATION_META)
        assert not message.metadata.get(SKIP_USER_PERSIST_META)
        assert RECOVERY_INBOUND_METADATA_KEY not in message.metadata
        assert SESSION_MESSAGE_METADATA_KEY not in message.metadata
        assert "_work_report" not in message.metadata
        assert "_hidden_history" not in message.metadata
        assert message.metadata.get(DELIVERY_RUN_META) != "creating-delivery"
        delivery = await factory.create(message, key)
        await delivery.bind_session_generation(replacement.generation)
        assert delivery.route.metadata[HISTORY_GENERATION_METADATA_KEY] == replacement.generation
        assert delivery.route.metadata[WEBUI_TURN_METADATA_KEY] != "creating-turn"
        assert delivery.route.metadata[WEBSOCKET_TURN_OWNER_METADATA_KEY] != "creating-owner"
        assert delivery.route.metadata["message_thread_id"] == 42
        current = await sessions.state.read_header(key)
        scope = WorkspaceScopeResolver(tmp_path, False).for_turn(
            channel="websocket", message_metadata=message.metadata, session_metadata=current.metadata,
        )
        assert scope.project_path == tmp_path
        assert scope.restrict_to_workspace is True
        assert await recorder.append_user_message(chat, message.content, metadata=delivery.route.metadata)
        seen.append(message)
        return OutboundMessage(channel="websocket", chat_id=chat, content="Done")

    try:
        if source == "cron":
            # Construct a legacy payload directly so write-time normalization
            # cannot conceal a missing read/dispatch-time migration.
            job = CronJob(id="saved", name="Reminder", payload=CronPayload(
                message="Check progress", session_key=key, origin_channel="websocket",
                origin_chat_id=chat, origin_metadata=origin,
            ))
            await run_bound_cron_job(job, agent=SimpleNamespace(submit_cron_turn=submit), cron=MagicMock())
        else:
            store = LocalTriggerStore(tmp_path / "triggers")
            trigger = store.create(name="Reminder", channel="websocket", chat_id=chat, session_key=key)
            trigger.origin_metadata = origin
            store._save_triggers_unlocked([trigger])
            store.enqueue(trigger.id, "Check progress")
            [delivery] = store.claim_deliveries()
            await _deliver_delivery(store, delivery, submit_turn=submit, is_channel_enabled=lambda _: True)
        assert len(seen) == 1
        assert await sessions.state.project_history(key, lambda history: history.turn_count) == 1
        assert origin == _creating_turn(header.generation, tmp_path)
    finally:
        await sessions.state.aclose()


@pytest.mark.parametrize("source", ["cron", "trigger"])
async def test_new_automation_stores_routing_without_turn_lifecycle(tmp_path, source):
    origin = _creating_turn("creating-generation", tmp_path)
    if source == "cron":
        service = CronService(tmp_path / "jobs.json")
        with request_context(RequestContext(
            channel="websocket", chat_id="reminder", session_key="websocket:reminder", metadata=origin,
        )):
            result = await CronTool(service).execute(action="add", message="Check progress", every_seconds=60)
        assert not getattr(result, "is_error", False), result
        [job] = service.list_jobs()
        saved = job.payload.origin_metadata
    else:
        trigger = LocalTriggerStore(tmp_path / "triggers").create(
            name="Reminder", channel="websocket", chat_id="reminder",
            session_key="websocket:reminder", origin_metadata=origin,
        )
        saved = trigger.origin_metadata
    assert saved == {"message_thread_id": 42}
    assert origin == _creating_turn("creating-generation", tmp_path)
