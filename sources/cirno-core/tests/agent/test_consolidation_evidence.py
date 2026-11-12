"""Archive citations stay exact, unambiguous and independent of model counting."""

import pytest

from cirno_core.memory.consolidation_contract import EvidenceRef, LearningPlan
from cirno_core.memory.consolidation_evidence import LearningEvidenceError, resolve_message
from cirno_core.memory.consolidation_learning import ConsolidationLearning
from cirno_core.session.keys import ROUTER_SESSION_KEY


def test_unique_quote_resolves_without_counting_prior_context():
    messages = [{"role": "tool", "content": f"Result {i}: verified sample"} for i in range(400)]
    ref = EvidenceRef(quote="Result 317: verified sample")
    assert resolve_message(messages, ref) == 317
    # Explicit references remain strict; no guessed relocation or fuzzy matching.
    with pytest.raises(LearningEvidenceError, match="index 0"):
        resolve_message(messages, ref.model_copy(update={"message": 0}))


def test_ambiguous_or_paraphrased_quotes_cannot_become_evidence():
    messages = [{"role": "user", "content": "Value 43.2 verified"}] * 2
    with pytest.raises(LearningEvidenceError, match="multiple"):
        resolve_message(messages, EvidenceRef(quote="Value 43.2 verified"))
    with pytest.raises(LearningEvidenceError, match="does not match"):
        resolve_message(messages, EvidenceRef(quote="The verified value is 43.2"))
    assert resolve_message(messages, EvidenceRef(message=1, quote="Value 43.2 verified")) == 1


def test_multimodal_text_newlines_are_not_json_escapes_or_image_metadata():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "第一行\n第二行"},
                {"type": "image_url", "image_url": {"url": "private-image-reference"}},
            ],
        }
    ]
    assert resolve_message(messages, EvidenceRef(quote="第一行\n第二行")) == 0
    for quote in ("第一行\\n第二行", "private-image-reference"):
        with pytest.raises(LearningEvidenceError):
            resolve_message(messages, EvidenceRef(quote=quote))


def test_quote_only_profile_evidence_still_requires_actual_user(tmp_path):
    item = ConsolidationLearning(
        tmp_path,
        [{"role": "tool", "content": "Call the user Ada"}],
        session_key=ROUTER_SESSION_KEY,
        project_id=None,
        context_chars=16000,
        max_updates=8,
    )
    item.context()
    evidence = item.repo.archive_messages(item.messages, ROUTER_SESSION_KEY)
    plan = LearningPlan.model_validate(
        {
            "documents": [
                {
                    "path": "USER.md",
                    "content": "Name: Ada",
                    "evidence": [{"quote": "Call the user Ada"}],
                }
            ]
        }
    )
    with pytest.raises(ValueError, match="explicit user"):
        item.apply(plan, evidence, "checkpoint")
    assert not (tmp_path / "USER.md").exists()


def test_ordinary_archive_quotes_are_not_used_as_provenance_or_a_save_gate(tmp_path):
    item = ConsolidationLearning(
        tmp_path,
        [{"role": "tool", "content": "Measured 43.2 K"}],
        session_key="worker:a",
        project_id=None,
        context_chars=16000,
        max_updates=8,
    )
    item.context()
    evidence = item.repo.archive_messages(item.messages, "worker:a")
    plan = LearningPlan.model_validate(
        {
            "memories": [
                {
                    "kind": "fact",
                    "content": "Valid measurement",
                    "evidence": [{"quote": "Measured 43.2 K"}],
                },
                {
                    "kind": "fact",
                    "content": "Calibration was measured at 43.2 kelvin",
                    "evidence": [{"quote": "Measured 44 K"}],
                },
            ]
        }
    )
    item.apply(plan, evidence, "checkpoint")
    saved = item.repo.search(session_key="worker:a", layer="knowledge")["memories"]
    assert len(saved) == 2
    assert all(row["source_refs"] == [{"memory_id": evidence["id"], "revision": evidence["revision"]}] for row in saved)
