"""Harness-owned citations avoid asking the model to reproduce original wording."""

import json

import pytest

from cirno_core.memory.consolidation_contract import LearningPlan
from cirno_core.memory.consolidation_evidence import LearningEvidenceError
from cirno_core.memory.consolidation_learning import ConsolidationLearning
from cirno_core.memory.consolidation_receipts import retry_learning
from cirno_core.memory.consolidation_sources import archive_sources
from cirno_core.session.keys import ROUTER_SESSION_KEY


def make_learning(home, messages, session="worker:a"):
    learning = ConsolidationLearning(
        home, messages, session_key=session, project_id=None, context_chars=16000, max_updates=8
    )
    context = learning.context()
    evidence = learning.repo.archive_messages(messages, session)
    return learning, evidence, context


def finding(source_id, **extra):
    return {
        "content": "Verified calibration measured 43.2 K",
        "kind": "fact",
        "evidence": [{"source_id": source_id, **extra}],
    }


def test_source_catalogue_is_bounded_and_keeps_objective_and_latest_text():
    messages = [{"role": "user", "content": "Original objective"}] + [
        {"role": "tool", "content": f"Observation {i}: " + "x" * 2000} for i in range(1000)
    ]
    blocks, sources = archive_sources(messages, 1500)
    assert len("\n".join(blocks)) <= 1500
    assert {"archive:0", "archive:1000"} <= sources.keys()
    assert len(sources) < len(messages)
    assert [json.loads(block)["source_id"] for block in blocks] == list(sources)
    assert archive_sources(messages, 0) == ([], {})


def test_image_metadata_and_tool_call_arguments_are_not_offered_as_text_evidence():
    messages = [
        {"role": "assistant", "content": None, "tool_calls": [{"arguments": "invented fact"}]},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,private"}}
            ],
        },
        {"role": "tool", "content": [{"type": "text", "text": "真实文本\n第二行"}]},
    ]
    blocks, sources = archive_sources(messages, 2000)
    assert sources == {"archive:2": {"message": 2, "quote": "真实文本\n第二行"}}
    assert "private" not in "".join(blocks) and "invented fact" not in "".join(blocks)


def test_selected_handle_uses_original_text_even_if_model_adds_a_wrong_quote(tmp_path):
    messages = [{"role": "tool", "content": "测量值：43.2 K\n复核通过。"}]
    learning, evidence, context = make_learning(tmp_path, messages)
    assert '"source_id": "archive:0"' in context
    plan = LearningPlan.model_validate(
        {"memories": [finding("archive:0", quote="A paraphrased quote")]}
    )
    learning.apply(plan, evidence, "checkpoint")
    saved = learning.repo.search(session_key="worker:a", layer="knowledge")["memories"]
    assert saved[0]["source_refs"] == [
        {"message": 0, "memory_id": None, "quote": messages[0]["content"]}
    ]
    assert "A paraphrased quote" not in json.dumps(saved[0]["source_refs"])


def test_unoffered_handle_is_rejected_before_any_learning_write(tmp_path):
    learning, evidence, _ = make_learning(tmp_path, [{"role": "tool", "content": "Result"}])
    plan = LearningPlan.model_validate({"memories": [finding("archive:0"), finding("archive:999")]})
    with pytest.raises(LearningEvidenceError, match="not supplied"):
        learning.apply(plan, evidence, "checkpoint")
    assert not learning.repo.search(session_key="worker:a", layer="knowledge")["memories"]


@pytest.mark.parametrize("role", ["user", "tool"])
def test_profile_source_handles_preserve_actual_user_requirement(tmp_path, role):
    learning, evidence, _ = make_learning(
        tmp_path, [{"role": role, "content": "Call me Ada"}], ROUTER_SESSION_KEY
    )
    plan = LearningPlan.model_validate(
        {
            "documents": [
                {
                    "path": "USER.md",
                    "content": "Name: Ada",
                    "evidence": [{"source_id": "archive:0"}],
                }
            ]
        }
    )
    if role == "user":
        learning.apply(plan, evidence, "checkpoint")
        assert (tmp_path / "USER.md").read_text() == "Name: Ada"
    else:
        with pytest.raises(ValueError, match="explicit user"):
            learning.apply(plan, evidence, "checkpoint")
        assert not (tmp_path / "USER.md").exists()


def test_handle_receipts_can_retry_after_process_restart(tmp_path):
    path = tmp_path / "USER.md"
    path.write_text("Original")
    learning, evidence, _ = make_learning(
        tmp_path, [{"role": "user", "content": "Call me Ada"}], ROUTER_SESSION_KEY
    )
    plan = LearningPlan.model_validate(
        {
            "documents": [
                {
                    "path": "USER.md",
                    "content": "Original\nName: Ada",
                    "evidence": [{"source_id": "archive:0"}],
                }
            ]
        }
    )
    path.write_text("Concurrent owner edit")
    with pytest.raises(ValueError, match="changed during"):
        learning.apply(plan, evidence, "checkpoint")
    path.write_text("Original")
    assert retry_learning(learning.repo) == {"retried": 1}
    assert path.read_text() == "Original\nName: Ada"


def test_pending_handle_preserves_revision_and_private_scope_checks(tmp_path):
    learning, evidence, _ = make_learning(
        tmp_path, [{"role": "tool", "content": "Private result"}], ROUTER_SESSION_KEY
    )
    pending = learning.repo.save(
        "Shared original evidence", source="test:shared", session_key="worker:other", scope="user"
    )
    learning.context()
    source_id = "input:" + pending["id"]
    assert source_id in learning.sources
    mixed = finding(source_id)
    mixed["evidence"].append({"source_id": "archive:0"})
    with pytest.raises(ValueError, match="mix private"):
        learning.apply(LearningPlan.model_validate({"memories": [mixed]}), evidence, "checkpoint")
    learning.repo.save(
        "Changed original evidence",
        source="test:shared",
        session_key="worker:other",
        scope="user",
        memory_id=pending["id"],
        expected_revision=pending["revision"],
    )
    with pytest.raises(ValueError, match="changed during"):
        learning.apply(
            LearningPlan.model_validate({"memories": [finding(source_id)]}), evidence, "checkpoint"
        )


@pytest.mark.parametrize(
    "reference",
    [
        {"quote": "Rephrased, not an exact quotation"},
        {"message": 999, "quote": "Rephrased, not an exact quotation"},
        {"message": 0, "quote": "Repeated text"},
    ],
)
def test_ordinary_legacy_archive_references_use_batch_provenance(tmp_path, reference):
    messages = [{"role": "tool", "content": "Repeated text"}] * 2
    learning, evidence, _ = make_learning(tmp_path, messages)
    plan = LearningPlan.model_validate(
        {
            "memories": [
                {"kind": "observation", "content": "A task observation", "evidence": [reference]},
            ]
        }
    )
    learning.apply(plan, evidence, "checkpoint")
    saved = learning.repo.search(session_key="worker:a", layer="knowledge")["memories"]
    assert saved[0]["source_refs"] == [
        {"memory_id": evidence["id"], "revision": evidence["revision"]}
    ]


@pytest.mark.parametrize("scope", ["session", "user"])
def test_pending_input_still_requires_its_exact_revision_and_quote(tmp_path, scope):
    learning, evidence, _ = make_learning(
        tmp_path, [{"role": "tool", "content": "Private result"}], ROUTER_SESSION_KEY
    )
    pending = learning.repo.save(
        "Shared original input", source="test:input", session_key=ROUTER_SESSION_KEY, scope=scope
    )
    learning.context()
    plan = LearningPlan.model_validate(
        {
            "memories": [
                {
                    "kind": "lesson",
                    "content": "A derived lesson",
                    "evidence": [{"memory_id": pending["id"], "quote": "Rewritten quotation"}],
                },
            ]
        }
    )
    with pytest.raises(LearningEvidenceError, match="does not match its memory"):
        learning.apply(plan, evidence, "checkpoint")
    assert not learning.repo.search(session_key=ROUTER_SESSION_KEY, layer="knowledge")["memories"]


def test_pending_input_source_review_replays_previously_invalid_output_without_model(tmp_path):
    from cirno_core.memory.consolidation_contract import MARKER
    from cirno_core.memory.consolidation_receipts import invalid_output
    from cirno_memory.repository import MemoryRepository

    repo = MemoryRepository(tmp_path)
    pending = repo.save("Retain the measured result", source="test:input", session_key="worker:a")
    outside = repo.save("Other task input", source="test:input", session_key="worker:b")
    learning, evidence, _ = make_learning(tmp_path, [{"role": "user", "content": "Review findings"}])
    raw = "checkpoint" + MARKER + json.dumps({"reviewed_inputs": [
        {"source_id": "input:" + pending["id"], "reason": "retain"},
    ]})
    invalid_output(learning, evidence, raw, ValueError("Legacy schema required memory_id"))
    assert retry_learning(repo) == {"retried": 1}
    assert repo.consolidation_inputs("worker:a") == []
    assert repo.consolidation_inputs("worker:b")[0]["id"] == outside["id"]


@pytest.mark.parametrize("source_id", ["input:unoffered", "archive:0"])
def test_input_review_cannot_settle_unoffered_or_archive_sources(tmp_path, source_id):
    learning, evidence, _ = make_learning(tmp_path, [{"role": "user", "content": "Review findings"}])
    plan = LearningPlan.model_validate({"reviewed_inputs": [{"source_id": source_id, "reason": "retain"}]})
    with pytest.raises(LearningEvidenceError):
        learning.apply(plan, evidence, "checkpoint")


def test_learning_schema_errors_do_not_echo_input_values_or_help_urls():
    from pydantic import ValidationError
    from cirno_core.memory.consolidation_contract import output_error

    with pytest.raises(ValidationError) as captured:
        LearningPlan.model_validate({"reviewed_inputs": [{"source_id": "input:one", "reason": {"secret": "PRIVATE"}}]})
    detail = output_error(captured.value)
    assert "reviewed_inputs.0.reason" in detail
    assert "PRIVATE" not in detail and "https://" not in detail
