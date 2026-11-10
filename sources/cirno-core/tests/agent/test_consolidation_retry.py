"""Recovery must isolate failures and avoid replaying completed learning effects."""

import json

import pytest

from cirno_core.memory.consolidation_contract import LearningPlan
from cirno_core.memory.consolidation_learning import ConsolidationLearning
from cirno_core.memory.consolidation_receipts import PREFIX, retry_learning
from cirno_core.session.keys import ROUTER_SESSION_KEY


def profile_plan(home):
    (home / "USER.md").write_text("Original user", encoding="utf-8")
    messages = [{"role": "user", "content": "Call me Ada"}]
    learning = ConsolidationLearning(
        home,
        messages,
        session_key=ROUTER_SESSION_KEY,
        project_id=None,
        context_chars=16000,
        max_updates=8,
    )
    learning.context()
    evidence = learning.repo.archive_messages(messages, ROUTER_SESSION_KEY)
    plan = LearningPlan.model_validate(
        {
            "documents": [
                {
                    "path": "USER.md",
                    "content": "Name: Ada",
                    "evidence": [{"message": 0, "quote": "Call me Ada"}],
                }
            ]
        }
    )
    return learning, evidence, plan


def test_bad_batch_does_not_block_unrelated_recoverable_batch(tmp_path):
    learning, evidence, plan = profile_plan(tmp_path)
    path = tmp_path / "USER.md"
    path.write_text("Concurrent owner edit", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        learning.apply(plan, evidence, "checkpoint")
    path.write_text("Original user", encoding="utf-8")
    messages = [{"role": "user", "content": "Another unrelated task"}]
    bad = ConsolidationLearning(
        tmp_path,
        messages,
        session_key="worker:other",
        project_id=None,
        context_chars=16000,
        max_updates=8,
    )
    bad.context()
    other = bad.repo.archive_messages(messages, "worker:other")
    with pytest.raises(ValueError):
        bad.apply(plan, other, "unrelated checkpoint")
    result = retry_learning(learning.repo)
    assert result["retried"] == 1
    assert result["failures"][0]["source"] == other["id"]
    assert "writable" in result["failures"][0]["error"]
    assert path.read_text(encoding="utf-8") == "Name: Ada"


def test_stale_failure_index_cannot_reapply_completed_profile_change(tmp_path):
    learning, evidence, plan = profile_plan(tmp_path)
    learning.apply(plan, evidence, "checkpoint")
    path = tmp_path / "USER.md"
    path.write_text("A newer owner preference", encoding="utf-8")
    with learning.repo.connect() as db:
        row = db.execute(
            "SELECT value FROM maintenance WHERE key=?", (PREFIX + evidence["id"],)
        ).fetchone()
        metadata = json.loads(row[0])
        metadata["status"] = "failed"
        db.execute(
            "UPDATE maintenance SET value=? WHERE key=?",
            (json.dumps(metadata), PREFIX + evidence["id"]),
        )
    assert retry_learning(learning.repo) == {"retried": 1}
    assert path.read_text(encoding="utf-8") == "A newer owner preference"


def test_completed_plan_is_not_applied_again_or_replaced(tmp_path):
    learning, evidence, plan = profile_plan(tmp_path)
    learning.apply(plan, evidence, "checkpoint")
    (tmp_path / "USER.md").write_text("New preference", encoding="utf-8")
    learning.apply(plan, evidence, "checkpoint")
    assert (tmp_path / "USER.md").read_text(encoding="utf-8") == "New preference"
    with pytest.raises(ValueError, match="different completed plan"):
        learning.apply(LearningPlan(), evidence, "different checkpoint")


def test_corrupt_receipt_is_reported_and_rotated_without_starving_later_work(tmp_path):
    from cirno_core.memory.consolidation_receipts import receipt_path, write_receipt

    learning, evidence, plan = profile_plan(tmp_path)
    for index in range(11):
        record = {"source": f"corrupt-{index}", "session_key": "worker:other", "status": "failed"}
        write_receipt(learning.repo, record)
        receipt_path(learning.repo, record["source"]).write_text("invalid-json", encoding="utf-8")
    (tmp_path / "USER.md").write_text("Concurrent edit", encoding="utf-8")
    with pytest.raises(ValueError):
        learning.apply(plan, evidence, "checkpoint")
    (tmp_path / "USER.md").write_text("Original user", encoding="utf-8")
    result = retry_learning(learning.repo)
    assert result["retried"] == 0 and len(result["failures"]) == 10 and result["has_more"]
    result = retry_learning(learning.repo)
    assert result["retried"] == 1
    assert (tmp_path / "USER.md").read_text(encoding="utf-8") == "Name: Ada"
