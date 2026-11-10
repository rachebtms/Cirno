"""Source quotes, scope boundaries, self-improvement and retryable file conflicts."""

import pytest

from cirno_core.memory.consolidation_contract import LearningPlan
from cirno_core.memory.consolidation_learning import ConsolidationLearning
from cirno_core.memory.consolidation_receipts import outcomes, retry_learning
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.skills.history import skill_versions
from cirno_memory.repository import MemoryRepository

MESSAGES = [
    {"role": "user", "content": "Call me Ada. Use step 2 after step 1."},
    {"role": "tool", "content": "Verified step 1 and step 2 pass. Tested sample 17."},
]
SKILL = "---\nname: calibration\ndescription: Calibrate measured samples.\n---\n\nUse step 1.\n"


def learning(tmp_path, *, session="worker:a", project=None):
    item = ConsolidationLearning(
        tmp_path,
        MESSAGES,
        session_key=session,
        project_id=project,
        context_chars=16000,
        max_updates=8,
    )
    item.context()
    evidence = item.repo.archive_messages(MESSAGES, session, project)
    return item, evidence


def edit(path, content, message=0, quote="Call me Ada"):
    return {"path": path, "content": content, "evidence": [{"message": message, "quote": quote}]}


@pytest.mark.parametrize("session,project", [("worker:a", None), (ROUTER_SESSION_KEY, "project-a")])
def test_workers_and_project_batches_cannot_write_shared_user_identity(tmp_path, session, project):
    (tmp_path / "USER.md").write_text("Original user")
    item, evidence = learning(tmp_path, session=session, project=project)
    plan = LearningPlan.model_validate({"documents": [edit("USER.md", "Name: Ada")]})
    with pytest.raises(ValueError, match="not writable"):
        item.apply(plan, evidence, "checkpoint")
    assert (tmp_path / "USER.md").read_text() == "Original user"
    assert outcomes(item.repo)["consolidation_failed"] == 1


def test_router_profile_updates_require_actual_user_evidence_and_no_lost_edits(tmp_path):
    path = tmp_path / "USER.md"
    path.write_text("Original user")
    item, evidence = learning(tmp_path, session=ROUTER_SESSION_KEY)
    plan = LearningPlan.model_validate({"documents": [edit("USER.md", "Original user\nName: Ada")]})
    path.write_text("New owner edit")
    with pytest.raises(ValueError, match="changed during"):
        item.apply(plan, evidence, "checkpoint")
    assert path.read_text() == "New owner edit"
    # Retry the already-generated result without a provider call or re-summarization.
    path.write_text("Original user")
    assert retry_learning(item.repo) == {"retried": 1}
    assert path.read_text() == "Original user\nName: Ada"
    assert outcomes(item.repo)["consolidation_failed"] == 0


def test_tool_output_cannot_redefine_user_profile(tmp_path):
    item, evidence = learning(tmp_path, session=ROUTER_SESSION_KEY)
    plan = LearningPlan.model_validate(
        {"documents": [edit("USER.md", "Name: Ada", 1, "Verified step 1")]}
    )
    with pytest.raises(ValueError, match="explicit user"):
        item.apply(plan, evidence, "checkpoint")


def test_existing_skill_correction_is_validated_and_versioned_in_the_same_pass(tmp_path):
    path = tmp_path / "skills/calibration/SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(SKILL)
    # Mention the Skill so its entire current document is offered for replacement.
    messages = [
        *MESSAGES,
        {"role": "assistant", "content": "Correct calibration skill using verified steps."},
    ]
    item = ConsolidationLearning(
        tmp_path,
        messages,
        session_key="worker:a",
        project_id=None,
        context_chars=16000,
        max_updates=8,
    )
    item.context()
    evidence = item.repo.archive_messages(messages, "worker:a")
    changed = SKILL.replace(
        "Use step 1.", "Use step 1, then step 2. Tested sample 17; other samples untested."
    )
    item.apply(
        LearningPlan.model_validate(
            {"documents": [edit("skills/calibration/SKILL.md", changed, 1, "Tested sample 17")]}
        ),
        evidence,
        "checkpoint",
    )
    assert path.read_text() == changed
    assert len(skill_versions("calibration", tmp_path)) == 2


def test_new_skill_requires_an_independent_task_lesson(tmp_path):
    item, evidence = learning(tmp_path, project="project-a")
    document = edit("skills/calibration/SKILL.md", SKILL, 1, "Verified step 1")
    with pytest.raises(ValueError, match="another task"):
        item.apply(LearningPlan.model_validate({"documents": [document]}), evidence, "checkpoint")
    prior = item.repo.save(
        "Verified calibration workflow from sample 16",
        source="test:sample16",
        session_key="worker:previous",
        project_id="project-a",
        scope="project",
        kind="lesson",
        layer="knowledge",
        enqueue=False,
    )
    item.context()
    document["related_memory_ids"] = [prior["id"]]
    item.apply(LearningPlan.model_validate({"documents": [document]}), evidence, "checkpoint")
    assert (tmp_path / document["path"]).exists()
    assert skill_versions("calibration", tmp_path)[0]["validation"]["valid"]


def test_pending_inputs_are_scoped_and_only_reviewed_unchanged_revisions_settle(tmp_path):
    repo = MemoryRepository(tmp_path)
    old = repo.save("Verified old calibration finding", source="test:old", session_key="worker:a")
    changed = repo.save("Old revision", source="test:changed", session_key="worker:a")
    outside = repo.save("Private other task", source="test:outside", session_key="worker:b")
    item, evidence = learning(tmp_path)
    assert old["id"] in item.inputs and outside["id"] not in item.inputs
    repo.save(
        "New revision",
        source="test:changed",
        session_key="worker:a",
        memory_id=changed["id"],
        expected_revision=changed["revision"],
    )
    plan = LearningPlan.model_validate(
        {
            "reviewed_inputs": [
                {"memory_id": i, "reason": "Retain verified calibration finding"}
                for i in [old["id"], changed["id"]]
            ],
            "memories": [
                {
                    "content": "Old calibration finding was verified.",
                    "kind": "lesson",
                    "evidence": [
                        {"memory_id": old["id"], "quote": "Verified old calibration finding"}
                    ],
                }
            ],
        }
    )
    item.apply(plan, evidence, "checkpoint")
    remaining = {row["id"] for row in repo.consolidation_inputs("worker:a")}
    assert old["id"] not in remaining and changed["id"] in remaining
    assert repo.consolidation_inputs("worker:b")[0]["id"] == outside["id"]
    receipts = repo.receipts()["receipts"]
    assert len(receipts) == 1 and receipts[0]["outcome"] == "created"


def test_bad_quote_budget_and_traversal_are_rejected_before_any_document_write(tmp_path):
    item, evidence = learning(tmp_path, session=ROUTER_SESSION_KEY)
    for documents in (
        [edit("../USER.md", "Name: Ada")],
        [edit("USER.md", "Name: Ada", quote="invented")],
    ):
        with pytest.raises(ValueError):
            item.apply(
                LearningPlan.model_validate({"documents": documents}), evidence, "checkpoint"
            )
    assert not (tmp_path / "USER.md").exists()


@pytest.mark.parametrize("mixed", [False, True])
def test_router_shared_inputs_do_not_promote_private_task_evidence(tmp_path, mixed):
    repo = MemoryRepository(tmp_path)
    shared = repo.save(
        "Shared verified lesson",
        source="test:shared",
        session_key="worker:old",
        scope="user",
        kind="lesson",
    )
    item, evidence = learning(tmp_path, session=ROUTER_SESSION_KEY)
    refs = [{"memory_id": shared["id"], "quote": "Shared verified lesson"}]
    if mixed:
        refs.append({"message": 1, "quote": "Tested sample 17"})
    plan = LearningPlan.model_validate(
        {"memories": [{"content": "Reusable shared method", "kind": "lesson", "evidence": refs}]}
    )
    if mixed:
        with pytest.raises(ValueError, match="mix private"):
            item.apply(plan, evidence, "checkpoint")
        assert not repo.search(maintenance=True, layer="knowledge")["memories"]
    else:
        item.apply(plan, evidence, "checkpoint")
        saved = repo.search(maintenance=True, layer="knowledge")["memories"]
        assert len(saved) == 1 and saved[0]["scope"] == "user"
        assert saved[0]["based_on"] == shared["id"]


def test_changed_evidence_cannot_be_used_to_save_a_new_finding(tmp_path):
    repo = MemoryRepository(tmp_path)
    source = repo.save("Before correction", source="test:old", session_key="worker:a")
    item, evidence = learning(tmp_path)
    repo.save(
        "After correction",
        source="test:new",
        session_key="worker:a",
        memory_id=source["id"],
        expected_revision=source["revision"],
    )
    plan = LearningPlan.model_validate(
        {
            "memories": [
                {
                    "content": "Stale claim",
                    "kind": "fact",
                    "evidence": [{"memory_id": source["id"], "quote": "Before correction"}],
                }
            ]
        }
    )
    with pytest.raises(ValueError, match="evidence changed"):
        item.apply(plan, evidence, "checkpoint")
    assert not repo.search(session_key="worker:a", layer="knowledge")["memories"]
