from __future__ import annotations

import pytest

from cirno.bus.outbound_events import (
    ContextCompactionEvent,
    RecoveryStateEvent,
    RetryStatusEvent,
    TurnEndEvent,
)
from cirno.bus.agent_events import CompactionReason
from cirno.providers.base import LLMUsage
from cirno.webui.metadata import WEBUI_TURN_METADATA_KEY
from cirno.webui.outbound_wire import (
    encode_context_compaction,
    encode_recovery_state,
    encode_retry_status,
    encode_turn_end,
)


@pytest.mark.parametrize("reason", [None, "idle", "context_pressure", "manual", "provider_native"])
def test_encode_context_compaction_projects_the_lifecycle(reason: CompactionReason | None) -> None:
    payload = encode_context_compaction(
        "chat-1",
        ContextCompactionEvent(
            compaction_id="compact-1",
            phase="succeeded",
            reason=reason,
        ),
    )

    assert payload == {
        "event": "context_compaction",
        "chat_id": "chat-1",
        "compaction_id": "compact-1",
        "phase": "succeeded",
        **({"reason": reason} if reason is not None else {}),
    }


def test_encode_recovery_state_omits_absent_optional_fields() -> None:
    payload = encode_recovery_state(
        "chat-1",
        RecoveryStateEvent(
            status="running",
            recovery_id="recovery-1",
            reason="",
            attempts=0,
        ),
    )

    assert payload == {
        "event": "recovery_state",
        "chat_id": "chat-1",
        "status": "running",
        "recovery_id": "recovery-1",
        "attempts": 0,
    }


def test_encode_recovery_state_preserves_false_can_continue() -> None:
    payload = encode_recovery_state(
        "chat-1",
        RecoveryStateEvent(
            status="awaiting_user",
            recovery_id="recovery-1",
            reason="tool_state_unknown",
            attempts=1,
            can_continue=False,
        ),
    )

    assert payload == {
        "event": "recovery_state",
        "chat_id": "chat-1",
        "status": "awaiting_user",
        "recovery_id": "recovery-1",
        "attempts": 1,
        "reason": "tool_state_unknown",
        "can_continue": False,
    }


def test_encode_retry_status_projects_relative_wait_and_turn_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cirno.webui.outbound_wire.time.time", lambda: 120.0)

    payload = encode_retry_status(
        "chat-1",
        RetryStatusEvent(
            state="waiting",
            attempt=2,
            max_attempts=4,
            error_kind="connection",
            next_retry_at=123.5,
        ),
        {WEBUI_TURN_METADATA_KEY: "turn-1", "private": "must-not-leak"},
    )

    assert payload == {
        "event": "retry_status",
        "chat_id": "chat-1",
        "turn_id": "turn-1",
        "state": "waiting",
        "attempt": 2,
        "max_attempts": 4,
        "error_kind": "connection",
        "retry_after_s": 3.5,
    }


def test_encode_turn_end_omits_absent_fields_and_private_metadata() -> None:
    payload = encode_turn_end(
        "chat-1",
        TurnEndEvent(),
        {WEBUI_TURN_METADATA_KEY: 42, "private": "must-not-leak"},
    )

    assert payload == {"event": "turn_end", "chat_id": "chat-1"}


def test_encode_turn_end_projects_complete_wire_contract() -> None:
    usage = LLMUsage.reported(
        input_tokens=80,
        output_tokens=20,
        cache_read_tokens=40,
    ).with_timing(generation_ms=500, ttft_ms=125)
    goal_state = {"active": True, "ui_summary": "Explore codebase"}

    payload = encode_turn_end(
        "chat-1",
        TurnEndEvent(
            latency_ms=1500,
            goal_state=goal_state,
            usage=usage,
            round_usages=(usage,),
            context_window_tokens=128_000,
            outcome="error",
            failure_kind="provider",
            failure_error_kind="connection",
            failure_attempts=4,
            failure_message="Connection refused",
        ),
        {WEBUI_TURN_METADATA_KEY: "turn-1", "private": "must-not-leak"},
    )

    assert payload == {
        "event": "turn_end",
        "chat_id": "chat-1",
        "turn_id": "turn-1",
        "latency_ms": 1500,
        "goal_state": goal_state,
        "usage": usage.to_turn_dict(),
        "round_usages": [usage.to_turn_dict()],
        "context_window_tokens": 128_000,
        "outcome": "error",
        "failure_kind": "provider",
        "failure_error_kind": "connection",
        "failure_attempts": 4,
        "failure_message": "Connection refused",
    }


@pytest.mark.parametrize("preserved", [False, True])
def test_encode_recovery_state_reports_reply_preservation(preserved: bool) -> None:
    payload = encode_recovery_state(
        "chat-1",
        RecoveryStateEvent(
            status="awaiting_user", recovery_id="recovery-1",
            reason="model_request_failed", failure_error_kind="connection",
            reply_preserved=preserved,
        ),
    )
    assert payload["reply_preserved"] is preserved
    assert payload["status"] == "awaiting_user"
    assert payload["failure_error_kind"] == "connection"


def test_compaction_details_survive_history_projection():
    from cirno.webui.transcript import _client_projection_event

    failed = encode_context_compaction("chat", ContextCompactionEvent(
        compaction_id="failed", phase="failed", reason="idle", error="ReadTimeout: model unavailable",
    ))
    succeeded = encode_context_compaction("chat", ContextCompactionEvent(
        compaction_id="success", phase="succeeded", reason="idle",
        context_tokens=1200, context_window_tokens=512000, context_estimated=True,
    ))
    assert failed["error"] == "ReadTimeout: model unavailable"
    assert succeeded["context_tokens"] == 1200
    assert _client_projection_event(failed, augment_user_media=None, augment_assistant_media=None, augment_assistant_text=None)["error"] == failed["error"]
    assert _client_projection_event(succeeded, augment_user_media=None, augment_assistant_media=None, augment_assistant_text=None)["context_tokens"] == 1200


def test_async_question_survives_history_and_legacy_session_projection():
    from cirno.webui.transcript import _client_projection_event, _session_assistant_event
    blob = {'kind': 'user_question', 'data': {'id': 'a' * 32, 'question': 'Which format?', 'options': ['CSV'], 'assumption': ''}}
    for record in (
        {'event': 'message', 'chat_id': 'one', 'text': 'Which format?', 'agent_ui': blob},
        _session_assistant_event('websocket:one', {'role': 'assistant', 'content': 'Which format?', 'agent_ui': blob}),
    ):
        assert record['agent_ui'] == blob
        projected = _client_projection_event(record, augment_user_media=None, augment_assistant_media=None, augment_assistant_text=None)
        assert projected['agent_ui'] == blob
