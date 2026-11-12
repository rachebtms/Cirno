"""One awaited request makes both a checkpoint and grounded durable learning."""

import asyncio
import json
import threading
from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.config.schema import Config
from cirno_core.memory.archiver import MemoryArchiver
from cirno_core.memory.consolidation_contract import MARKER
from cirno_core.memory.consolidation_learning import ConsolidationLearning
from cirno_core.memory.consolidation_receipts import retry_learning
from cirno_core.memory.consolidation_recovery import retry_session_learning
from cirno_core.session.model import Session
from cirno_core.memory.store import MemoryStore
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.generation import GenerationSettings
from cirno_core.utils.llm_runtime import LLMRuntime
from cirno_memory.repository import MemoryRepository

CHECKPOINT = "## Task\nMeasure calibration.\n## State\nVerified value 43.2.\n## Next\nTask complete.\n## Retained facts\n(none)"
MESSAGES = [
    {"role": "user", "content": "Measure calibration"},
    {"role": "tool", "content": "Calibration measurement: 43.2 at 280 K"},
]


def result(**updates):
    return CHECKPOINT + MARKER + json.dumps(updates)


def fixture(tmp_path, answer):
    provider = MagicMock(spec=LLMProvider)
    provider.chat_stream_with_retry = AsyncMock(return_value=LLMResponse(content=answer))
    runtime = LLMRuntime(provider, "fixture", GenerationSettings(max_tokens=8192), 512000)
    return MemoryArchiver(MemoryStore(tmp_path), lambda **kw: [], lambda _: []), runtime


def finding(**extra):
    return dict(
        content="Calibration measured 43.2 at 280 K.",
        kind="fact",
        evidence=[{"message": 1, "quote": "43.2 at 280 K"}],
        **extra,
    )


async def test_one_request_preserves_cache_prefix_and_saves_scoped_knowledge(tmp_path):
    archiver, runtime = fixture(tmp_path, result(memories=[finding()]))
    history = [{"role": "system", "content": "Stable system prefix"}, *deepcopy(MESSAGES)]
    tools = [{"type": "function", "function": {"name": "shell__exec", "parameters": {}}}]
    original = deepcopy(history)
    summary = await archiver.archive(
        MESSAGES,
        runtime=runtime,
        session_key="websocket:worker",
        history=history,
        request_tools=tools,
        project_id="project-a",
    )
    assert summary == CHECKPOINT
    assert runtime.provider.chat_stream_with_retry.await_count == 1
    call = runtime.provider.chat_stream_with_retry.call_args.kwargs
    assert call["messages"][:-1] == history == original
    assert call["tools"] == tools
    assert "Durable learning in this same response" in call["messages"][-1]["content"]
    repo = MemoryRepository(tmp_path)
    saved = repo.search(session_key="websocket:worker", project_id="project-a", layer="knowledge")[
        "memories"
    ]
    assert len(saved) == 1 and saved[0]["scope"] == "project"
    assert repo.read(saved[0]["based_on"], project_id="project-a")["layer"] == "source"
    assert not repo.search(
        session_key="websocket:other", project_id="project-b", layer="knowledge"
    )["memories"]
    assert "Memory updates" not in summary
    # Same evidence and output cannot create duplicate knowledge.
    await archiver.archive(
        MESSAGES,
        runtime=runtime,
        session_key="websocket:worker",
        history=history,
        request_tools=tools,
        project_id="project-a",
    )
    assert len(repo.search(project_id="project-a", layer="knowledge")["memories"]) == 1


async def test_consolidation_source_handles_need_no_model_written_quote_or_extra_request(tmp_path):
    update = finding()
    update["evidence"] = [{"source_id": "archive:1"}]
    archiver, runtime = fixture(tmp_path, result(memories=[update]))
    history = [{"role": "system", "content": "Stable cached prefix"}, *deepcopy(MESSAGES)]
    kwargs = dict(runtime=runtime, session_key="worker:one", history=history, request_tools=[])
    assert await archiver.archive(MESSAGES, **kwargs) == CHECKPOINT
    call = runtime.provider.chat_stream_with_retry.call_args.kwargs
    assert call["messages"][:-1] == history
    assert '"source_id": "archive:1"' in call["messages"][-1]["content"]
    assert "omit evidence" in call["messages"][-1]["content"]
    assert await archiver.archive(MESSAGES, **kwargs) == CHECKPOINT
    runtime.provider.chat_stream_with_retry.assert_awaited_once()
    saved = MemoryRepository(tmp_path).search(session_key="worker:one", layer="knowledge")["memories"]
    assert saved[0]["source_refs"][0]["quote"] == MESSAGES[1]["content"]


async def test_learning_finishes_before_owning_task_can_resume_and_cancellation_drains(
    tmp_path, monkeypatch
):
    archiver, runtime = fixture(tmp_path, result(memories=[finding()]))
    entered, release = threading.Event(), threading.Event()
    original = ConsolidationLearning.apply

    def apply(*args):
        entered.set()
        release.wait(3)
        original(*args)

    monkeypatch.setattr(ConsolidationLearning, "apply", apply)
    task = asyncio.create_task(
        archiver.archive(
            MESSAGES, runtime=runtime, session_key="worker:one", history=MESSAGES, request_tools=[]
        )
    )
    assert await asyncio.to_thread(entered.wait, 2)
    assert not task.done()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done(), "cancellation must settle accepted writes before ownership is released"
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    repo = MemoryRepository(tmp_path)
    assert len(repo.search(session_key="worker:one", layer="knowledge")["memories"]) == 1
    runtime.provider.chat_stream_with_retry.assert_awaited_once()


async def test_learning_can_be_disabled_without_disabling_checkpoint(tmp_path):
    archiver, runtime = fixture(tmp_path, CHECKPOINT)
    summary = await archiver.archive(
        MESSAGES,
        runtime=replace(runtime, consolidation_learn=False),
        session_key="worker:one",
        history=MESSAGES,
        request_tools=[],
    )
    assert summary == CHECKPOINT
    assert (
        "Durable learning"
        not in runtime.provider.chat_stream_with_retry.call_args.kwargs["messages"][-1]["content"]
    )
    assert not MemoryRepository(tmp_path).search(session_key="worker:one", layer="knowledge")[
        "memories"
    ]


async def test_invalid_learning_plan_keeps_checkpoint_and_reports_deferred_learning(tmp_path):
    archiver, runtime = fixture(tmp_path, CHECKPOINT + MARKER + '{"memories": [invalid]}')
    summary = await archiver.archive(
        MESSAGES, runtime=runtime, session_key="worker:one", history=MESSAGES, request_tools=[]
    )
    assert summary == CHECKPOINT
    assert summary.learning_failure["pending"][0]["kind"] == "updates"
    repo = MemoryRepository(tmp_path)
    assert repo.search(session_key="worker:one", layer="source")["memories"]
    assert repo.search(session_key="worker:one", layer="task")["memories"]
    runtime.provider.chat_stream_with_retry.assert_awaited_once()


def test_old_settings_load_into_unified_configuration_and_old_scheduler_is_not_saved():
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "compaction": {"maxTokens": 4096},
                    "dream": {"enabled": False, "mode": "interval"},
                }
            }
        }
    )
    assert config.agents.defaults.consolidation.max_tokens == 4096
    assert config.agents.defaults.consolidation.learn is False
    saved = config.model_dump(by_alias=True)["agents"]["defaults"]
    assert "dream" not in saved and "compaction" not in saved
    assert saved["consolidation"]["maxTokens"] == 4096


async def test_failed_learning_save_reuses_generated_checkpoint_without_another_model_call(
    tmp_path, monkeypatch
):
    archiver, runtime = fixture(tmp_path, result(memories=[finding()]))
    apply = ConsolidationLearning._apply
    attempts = 0

    def fail_once(*args):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("storage temporarily unavailable")
        return apply(*args)

    monkeypatch.setattr(ConsolidationLearning, "_apply", fail_once)
    kwargs = dict(runtime=runtime, session_key="worker:one", history=MESSAGES, request_tools=[])
    summary = await archiver.archive(MESSAGES, **kwargs)
    assert summary == CHECKPOINT
    assert "storage temporarily" in summary.learning_failure["error"]
    assert await archiver.archive(MESSAGES, **kwargs) == CHECKPOINT
    assert retry_learning(MemoryRepository(tmp_path)) == {"retried": 1}
    runtime.provider.chat_stream_with_retry.assert_awaited_once()


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("invalid_ref", [
    {"message": 0, "quote": "43.2 at 280 K"},
    {"quote": "Calibration was measured at 43.2 Kelvin"},
])
@pytest.mark.parametrize("recovery", ["command", "memory"])
async def test_retained_legacy_quote_failure_can_be_saved_without_regeneration(
    tmp_path, monkeypatch, legacy, invalid_ref, recovery
):
    from cirno_core.memory.consolidation_receipts import receipt_path

    invalid = finding()
    invalid["evidence"] = [invalid_ref]
    archiver, runtime = fixture(tmp_path, result(memories=[invalid]))
    kwargs = dict(runtime=runtime, session_key="worker:one", history=MESSAGES, request_tools=[])
    apply = ConsolidationLearning._apply

    def old_apply(self, plan, evidence):
        for item in plan.memories:
            self._evidence(item.evidence)
        return apply(self, plan, evidence)

    # Reproduce the receipt left by the released pre-fix validator.
    with monkeypatch.context() as patch:
        patch.setattr(ConsolidationLearning, "_apply", old_apply)
        summary = await archiver.archive(MESSAGES, **kwargs)
    assert summary == CHECKPOINT
    assert "quote does not match" in summary.learning_failure["error"]
    repo = MemoryRepository(tmp_path)
    source = repo.search(session_key="worker:one", layer="source")["memories"][0]
    if legacy:
        path = receipt_path(repo, source["id"])
        receipt = json.loads(path.read_text())
        receipt.pop("regenerate_output")
        receipt["error"] = "ValueError: Learning evidence quote does not match the archived message"
        path.write_text(json.dumps(receipt))
    # First consolidation after upgrading retains the old checkpoint and warning.
    cached = await archiver.archive(MESSAGES, **kwargs)
    assert cached == CHECKPOINT and cached.learning_failure["source"] == source["id"]
    journal = list(archiver.store.journal.iter_valid_entries())
    if recovery == "command":
        retried = await retry_session_learning(archiver, Session(key="worker:one"), runtime)
    else:
        retried = retry_learning(repo)
    assert retried["retried"] == 1
    runtime.provider.chat_stream_with_retry.assert_awaited_once()
    saved = repo.search(session_key="worker:one", layer="knowledge")["memories"]
    assert len(saved) == 1
    assert saved[0]["source_refs"] == [{"memory_id": source["id"], "revision": source["revision"]}]
    assert list(archiver.store.journal.iter_valid_entries()) == journal
    assert await archiver.archive(MESSAGES, **kwargs) == CHECKPOINT
    runtime.provider.chat_stream_with_retry.assert_awaited_once()


@pytest.mark.parametrize("after_append", [False, True])
async def test_completed_learning_survives_checkpoint_commit_retry_without_duplicate_effects(tmp_path, monkeypatch, after_append):
    archiver, runtime = fixture(tmp_path, result(memories=[finding()]))
    append = archiver.store.journal.append_history
    apply = ConsolidationLearning._apply
    applications = []
    def track(*args):
        applications.append(True)
        return apply(*args)
    monkeypatch.setattr(ConsolidationLearning, "_apply", track)
    def interrupted(*args, **kwargs):
        if after_append:
            append(*args, **kwargs)
        raise OSError("checkpoint commit interrupted")
    monkeypatch.setattr(archiver.store.journal, "append_history", interrupted)
    kwargs = dict(runtime=runtime, session_key="worker:one", history=MESSAGES, request_tools=[])
    with pytest.raises(OSError, match="commit interrupted"):
        await archiver.archive(MESSAGES, **kwargs)
    monkeypatch.setattr(archiver.store.journal, "append_history", append)
    assert await archiver.archive(MESSAGES, **kwargs) == CHECKPOINT
    runtime.provider.chat_stream_with_retry.assert_awaited_once()
    assert len(applications) == 1
    assert len(list(archiver.store.journal.iter_valid_entries())) == 1


async def test_pending_generated_plan_is_recovered_after_interrupted_process(tmp_path, monkeypatch):
    archiver, runtime = fixture(tmp_path, result(memories=[finding()]))
    apply = ConsolidationLearning._apply
    class ProcessCrash(BaseException):
        pass
    def crash(*args):
        raise ProcessCrash("simulated process crash")
    monkeypatch.setattr(ConsolidationLearning, "_apply", crash)
    kwargs = dict(runtime=runtime, session_key="worker:one", history=MESSAGES, request_tools=[])
    with pytest.raises(ProcessCrash, match="process crash"):
        await archiver.archive(MESSAGES, **kwargs)
    monkeypatch.setattr(ConsolidationLearning, "_apply", apply)
    assert await archiver.archive(MESSAGES, **kwargs) == CHECKPOINT
    runtime.provider.chat_stream_with_retry.assert_awaited_once()


def test_unified_settings_override_legacy_values_without_discarding_other_budgets():
    config = Config.model_validate(
        {
            "agents": {
                "defaults": {
                    "compaction": {"maxTokens": 4096, "reasoningEffort": "none"},
                    "consolidation": {"max_tokens": 2048, "learn": True},
                    "dream": {"enabled": False},
                }
            }
        }
    )
    assert config.agents.defaults.consolidation.max_tokens == 2048
    assert config.agents.defaults.consolidation.reasoning_effort == "none"
    assert config.agents.defaults.consolidation.learn is True


async def test_instruction_prefixes_are_not_numbered_as_learning_evidence(tmp_path):
    archiver, runtime = fixture(tmp_path, result(memories=[finding()]))
    source = [{"role": "developer", "content": "Stable developer instruction"}, *MESSAGES]
    summary = await archiver.archive(source, runtime=runtime, session_key="worker:one",
                                    history=source, request_tools=[])
    assert summary == CHECKPOINT
    call = runtime.provider.chat_stream_with_retry.call_args.kwargs
    assert call["messages"][:-1] == source
    repo = MemoryRepository(tmp_path)
    saved = repo.search(session_key="worker:one", layer="knowledge")["memories"][0]
    evidence = repo.read(saved["based_on"], session_key="worker:one")
    import json
    lines = (tmp_path / evidence["source"]).read_text().splitlines()
    assert [json.loads(line)["role"] for line in lines] == ["user", "tool"]


async def test_four_new_ordinary_findings_save_despite_old_style_model_quotations(tmp_path):
    updates = [{
        "kind": "lesson", "content": f"Research lesson {i}",
        "evidence": [{"message": 500 + i, "quote": f"Rephrased model excerpt {i}"}],
    } for i in range(4)]
    archiver, runtime = fixture(tmp_path, result(memories=updates))
    summary = await archiver.archive(MESSAGES, runtime=runtime, session_key="worker:one", history=MESSAGES, request_tools=[])
    assert summary == CHECKPOINT and getattr(summary, "learning_failure", None) is None
    repo = MemoryRepository(tmp_path)
    saved = repo.search(session_key="worker:one", layer="knowledge")["memories"]
    assert len(saved) == 4
    assert all(row["source_refs"] == [{"memory_id": row["based_on"], "revision": 1}] for row in saved)
    runtime.provider.chat_stream_with_retry.assert_awaited_once()
