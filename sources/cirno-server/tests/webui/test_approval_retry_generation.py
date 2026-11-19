"""Retrying delivery never makes a decision valid for a replacement conversation."""

from types import SimpleNamespace

import pytest
from cirno_core.security.approval.store import ApprovalStore


@pytest.mark.parametrize("generation", [None, "replacement-generation"])
@pytest.mark.parametrize("approved", [False, True])
def test_decision_delivery_retry_rechecks_conversation_generation(tmp_path, generation, approved):
    store = ApprovalStore(tmp_path / "approvals.sqlite3")
    request = SimpleNamespace(session_key="websocket:fixture", session_generation="original", turn_id="turn")
    item = store.record("fingerprint", request, {"tool": "fixture", "arguments": {}}, "pending", "owner decision")
    decision = store.decide(item["id"], approved=approved, generation="original")
    assert decision["wake_pending"] == 1
    with pytest.raises(ValueError, match="conversation was replaced"):
        store.decide(item["id"], approved=approved, generation=generation)
    saved = store.get(item["id"])
    assert saved["status"] == ("approved" if approved else "denied") and saved["wake_pending"] == 1


@pytest.mark.parametrize("approved", [False, True])
def test_unchanged_generation_can_retry_pending_decision_delivery(tmp_path, approved):
    store = ApprovalStore(tmp_path / "approvals.sqlite3")
    request = SimpleNamespace(session_key="websocket:fixture", session_generation="original", turn_id="turn")
    item = store.record("fingerprint", request, {"tool": "fixture", "arguments": {}}, "pending", "decision")
    decision = store.decide(item["id"], approved=approved, generation="original")
    assert store.decide(item["id"], approved=approved, generation="original") == decision
