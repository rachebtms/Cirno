"""Compaction explanations shown live must survive durable replay."""

import pytest

from cirno_core.session.presentation_history import fact_from_record, record_from_fact


@pytest.mark.parametrize(
    "phase,details",
    [
        (
            "succeeded",
            {
                "context_tokens": 4721,
                "context_window_tokens": 131072,
                "context_estimated": True,
                "evidence_checkpoint": True,
            },
        ),
        ("failed", {"error": "Provider disconnected before producing a checkpoint"}),
        ("succeeded", {"learning_failure": {"source": "source-original", "error": "Could not save USER.md",
                                          "saved": [{"id": "memory:0", "kind": "memory", "label": "Result"}],
                                          "pending": [{"id": "document:0", "kind": "document", "label": "USER.md"}]}}),
    ],
)
def test_compaction_fact_preserves_progress_and_failure_details(phase, details):
    record = {
        "event": "context_compaction",
        "chat_id": "research",
        "turn_id": "long-task",
        "compaction_id": "checkpoint-17",
        "phase": phase,
        "reason": "context_pressure",
        **details,
    }
    replay = record_from_fact(fact_from_record(record), "websocket:research")
    for field, value in details.items():
        assert replay[field] == value
    assert replay["reason"] == "context_pressure"


def test_learning_recovery_report_survives_durable_projection():
    from cirno_core.bus.agent_events import ContextCompactionEvent
    from cirno_core.memory.consolidation_retry_report import empty_report
    from cirno_core.session.outbound_wire import encode_context_compaction

    report = empty_report("source-retained")
    report.update(mode="replay", outcome="completed", saved=[{"id": "memory:0", "kind": "memory", "label": "Verified result"}])
    event = ContextCompactionEvent("retry-1", "succeeded", reason="manual", learning_retry=report)
    record = encode_context_compaction("research", event)
    replay = record_from_fact(fact_from_record(record), "websocket:research")
    assert replay["learning_retry"] == report
