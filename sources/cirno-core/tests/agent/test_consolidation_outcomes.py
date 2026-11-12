"""Task continuation, independent learning recovery and explicit retry budgets."""

import asyncio
import json
from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from cirno_core.agent.context import TranscriptInput
from cirno_core.agent.governance.state import ContextCompactionState
from cirno_core.config.models import ConsolidationConfig
from cirno_core.memory.archiver import MemoryArchiver
from cirno_core.memory.consolidation_contract import MARKER
from cirno_core.memory.consolidation_receipts import outcomes
from cirno_core.memory.consolidation_recovery import retry_session_learning
from cirno_core.memory.store import MemoryStore
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.generation import GenerationSettings
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.model import Session
from cirno_core.utils.llm_runtime import LLMRuntime
from cirno_memory.repository import MemoryRepository

CHECKPOINT = "## Task\nMeasure.\n## State\nMeasured 43.2 K.\n## Next\nContinue validation.\n## Retained facts\n(none)"
MESSAGES = [
    {"role": "user", "content": "Call me Ada"},
    {"role": "tool", "content": "Measured 43.2 K"},
]


def setup(home, output):
    provider = MagicMock(spec=LLMProvider)
    provider.chat_stream_with_retry = AsyncMock(return_value=LLMResponse(content=output))
    runtime = LLMRuntime(provider, "test", GenerationSettings(max_tokens=8192), 512000)
    archiver = MemoryArchiver(
        MemoryStore(home),
        lambda **kw: [{"role": "system", "content": "Stable"}, *kw["history"]],
        lambda _: [],
    )
    return archiver, runtime


async def archive(archiver, runtime, key=ROUTER_SESSION_KEY):
    return await archiver.archive(
        MESSAGES,
        runtime=runtime,
        session_key=key,
        history=[{"role": "system", "content": "Stable"}, *deepcopy(MESSAGES)],
        request_tools=[],
    )


async def test_ordinary_learning_binds_to_archive_without_model_evidence(tmp_path):
    archiver, runtime = setup(
        tmp_path,
        CHECKPOINT
        + MARKER
        + json.dumps({"memories": [{"content": "Measured 43.2 K", "kind": "observation"}]}),
    )
    assert await archive(archiver, runtime) == CHECKPOINT
    repo = MemoryRepository(tmp_path)
    saved = repo.search(session_key=ROUTER_SESSION_KEY, layer="knowledge")["memories"][0]
    assert saved["source_refs"][0]["memory_id"] == saved["based_on"]
    assert repo.read(saved["based_on"], session_key=ROUTER_SESSION_KEY)["layer"] == "source"
    runtime.provider.chat_stream_with_retry.assert_awaited_once()


async def test_partial_learning_failure_reports_saved_and_pending_then_retries_without_model(
    tmp_path, monkeypatch
):
    import cirno_core.memory.consolidation_learning as module

    (tmp_path / "USER.md").write_text("Original")
    plan = {
        "memories": [{"content": "Measured 43.2 K", "kind": "observation"}],
        "documents": [
            {
                "path": "USER.md",
                "content": "Original\nName: Ada",
                "evidence": [{"source_id": "archive:0"}],
            }
        ],
    }
    archiver, runtime = setup(tmp_path, CHECKPOINT + MARKER + json.dumps(plan))
    write = module.atomic_write_text

    def fail_profile(path, text):
        if path.name == "USER.md":
            raise OSError("profile disk unavailable")
        return write(path, text)

    monkeypatch.setattr(module, "atomic_write_text", fail_profile)
    result = await archive(archiver, runtime)
    assert result == CHECKPOINT
    failure = result.learning_failure
    assert [i["kind"] for i in failure["saved"]] == ["memory"]
    assert [i["label"] for i in failure["pending"]] == ["USER.md"]
    repo = MemoryRepository(tmp_path)
    assert outcomes(repo)["consolidation_failed"] == 1
    assert repo.search(session_key=ROUTER_SESSION_KEY, layer="task")["memories"]
    checkpoint_events = list(archiver.store.journal.iter_valid_entries())
    monkeypatch.setattr(module, "atomic_write_text", write)
    recovered = await retry_session_learning(archiver, Session(key=ROUTER_SESSION_KEY), runtime)
    assert recovered["retried"] == 1
    report = recovered["learning_retry"]
    assert report["mode"] == "replay" and report["model_called"] is False
    assert len(report["saved"]) == 2 and len(report["previously_saved"]) == 1
    assert [item["label"] for item in report["requested"]] == ["USER.md"]
    assert report["pending"] == []
    assert (tmp_path / "USER.md").read_text() == "Original\nName: Ada"
    assert outcomes(repo)["consolidation_failed"] == 0
    assert list(archiver.store.journal.iter_valid_entries()) == checkpoint_events
    assert len(repo.search(session_key=ROUTER_SESSION_KEY, layer="knowledge")["memories"]) == 1
    runtime.provider.chat_stream_with_retry.assert_awaited_once()


async def test_invalid_learning_and_checkpoint_commit_retry_keep_identical_summary(
    tmp_path, monkeypatch
):
    archiver, runtime = setup(tmp_path, CHECKPOINT + MARKER + '{"memories": broken}')
    append = archiver.store.journal.append_history
    monkeypatch.setattr(
        archiver.store.journal,
        "append_history",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("checkpoint disk unavailable")),
    )
    with pytest.raises(OSError, match="checkpoint disk"):
        await archive(archiver, runtime)
    monkeypatch.setattr(archiver.store.journal, "append_history", append)
    result = await archive(archiver, runtime)
    assert result == CHECKPOINT and result.learning_failure["pending"]
    runtime.provider.chat_stream_with_retry.assert_awaited_once()


@pytest.mark.parametrize("retries", [0, 2])
async def test_generation_retry_count_is_bounded_serial_and_does_not_apply_to_learning(
    tmp_path, retries
):
    archiver, runtime = setup(tmp_path, CHECKPOINT)
    active = 0
    calls = 0

    async def generate(**kwargs):
        nonlocal active, calls
        active += 1
        assert active == 1
        try:
            calls += 1
            await asyncio.sleep(0)
            if calls <= retries:
                raise RuntimeError("temporary model failure")
            return LLMResponse(content=CHECKPOINT)
        finally:
            active -= 1

    runtime.provider.chat_stream_with_retry.side_effect = generate
    result = await archive(archiver, replace(runtime, compaction_max_retries=retries))
    assert result == CHECKPOINT
    assert calls == retries + 1


@pytest.mark.parametrize("bad", [-1, 11, 1.5, True])
def test_retry_setting_rejects_invalid_values(bad):
    with pytest.raises(ValidationError):
        ConsolidationConfig(max_retries=bad)
    assert ConsolidationConfig(max_retries=0).max_retries == 0


def test_compaction_keeps_long_instruction_prefix_exact_and_does_not_rebuild_profiles():
    system = {"role": "system", "content": "stable-policy-" * 3000}
    developer = {"role": "developer", "content": "stable-tools-policy"}
    state = ContextCompactionState.from_messages(
        [system, developer, *deepcopy(MESSAGES)], AsyncMock(), None
    )
    original = deepcopy([system, developer])
    first = state.summary_transcript_builder("Checkpoint one")
    second = state.summary_transcript_builder("Checkpoint two")
    assert first[:2] == second[:2] == original
    assert first[2]["role"] == second[2]["role"] == "user"
    assert "Checkpoint one" not in second[2]["content"]
    assert len(second) == 3
    builds = 0

    def builder(transcript):
        nonlocal builds
        builds += 1
        return [
            deepcopy(system),
            *transcript.history,
            {"role": "user", "content": transcript.current_message},
        ]

    messages, scoped = ContextCompactionState.from_transcript(
        TranscriptInput(history=deepcopy(MESSAGES), current_message="Continue"),
        builder,
        AsyncMock(),
        None,
    )
    assert scoped.raw_accepted_boundary == len(messages) - 1
    assert scoped.summary_transcript_builder("New checkpoint")[0] == messages[0]
    assert builds == 1


async def test_cancelled_generation_is_not_retried_or_converted_to_learning_warning(tmp_path):
    archiver, runtime = setup(tmp_path, CHECKPOINT)
    runtime.provider.chat_stream_with_retry.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await archive(archiver, replace(runtime, compaction_max_retries=3))
    runtime.provider.chat_stream_with_retry.assert_awaited_once()


async def test_learning_reference_read_failure_does_not_block_checkpoint(tmp_path, monkeypatch):
    from cirno_core.memory.consolidation_learning import ConsolidationLearning

    archiver, runtime = setup(tmp_path, CHECKPOINT)
    read = ConsolidationLearning.context
    monkeypatch.setattr(
        ConsolidationLearning,
        "context",
        lambda _: (_ for _ in ()).throw(OSError("unreadable Skill reference")),
    )
    result = await archive(archiver, runtime)
    assert result == CHECKPOINT
    assert "unreadable Skill reference" in result.learning_failure["error"]
    assert result.learning_failure["source"]
    assert outcomes(MemoryRepository(tmp_path))["consolidation_failed"] == 1
    monkeypatch.setattr(ConsolidationLearning, "context", read)
    runtime.provider.chat_stream_with_retry.return_value = LLMResponse(
        content="## Memory updates\n{}"
    )
    retried = await retry_session_learning(archiver, Session(key=ROUTER_SESSION_KEY), runtime)
    assert retried["retried"] == 1
    assert runtime.provider.chat_stream_with_retry.await_count == 2


async def test_learning_parse_failure_when_disabled_keeps_valid_checkpoint(tmp_path):
    archiver, runtime = setup(tmp_path, CHECKPOINT + MARKER + '{"memories": invalid}')
    result = await archive(archiver, replace(runtime, consolidation_learn=False))
    assert result == CHECKPOINT and result.learning_failure["pending"]


async def test_over_budget_archive_retains_source_for_later_learning(tmp_path):
    archiver, runtime = setup(tmp_path, CHECKPOINT)
    session = Session(key=ROUTER_SESSION_KEY, messages=deepcopy(MESSAGES))
    result = await archiver.archive_session(
        session,
        archive_end=len(MESSAGES),
        runtime=runtime,
        input_token_budget=0,
    )
    assert result.learning_failure["source"]
    assert outcomes(MemoryRepository(tmp_path))["consolidation_failed"] == 1
    runtime.provider.chat_stream_with_retry.assert_not_awaited()
    runtime.provider.chat_stream_with_retry.return_value = LLMResponse(
        content="## Memory updates\n{}"
    )
    recovered = await retry_session_learning(archiver, session, runtime)
    assert recovered["retried"] == 1
    runtime.provider.chat_stream_with_retry.assert_awaited_once()


async def test_committed_generated_checkpoint_is_reused_even_with_zero_input_budget(tmp_path):
    archiver, runtime = setup(tmp_path, CHECKPOINT)
    assert await archive(archiver, runtime) == CHECKPOINT
    result = await archiver.archive(
        MESSAGES, runtime=runtime, session_key=ROUTER_SESSION_KEY,
        history=deepcopy(MESSAGES), request_tools=[], input_token_budget=0,
    )
    assert result == CHECKPOINT
    runtime.provider.chat_stream_with_retry.assert_awaited_once()


@pytest.mark.parametrize("updated_count", [0, 2])
async def test_learning_retry_reports_regenerated_items_and_empty_extraction(tmp_path, updated_count):
    proposals = [{"kind": "lesson", "content": f"Proposed lesson {i}", "evidence": [{"source_id": "archive:999"}]} for i in range(4)]
    archiver, runtime = setup(tmp_path, CHECKPOINT + MARKER + json.dumps({"memories": proposals}))
    first = await archive(archiver, runtime)
    assert first.learning_failure
    journal = list(archiver.store.journal.iter_valid_entries())
    updates = [{"kind": "lesson", "content": f"Confirmed lesson {i}"} for i in range(updated_count)]
    runtime.provider.chat_stream_with_retry.return_value = LLMResponse(content="## Memory updates\n" + json.dumps({"memories": updates}))
    recovered = await retry_session_learning(archiver, Session(key=ROUTER_SESSION_KEY), runtime)
    report = recovered["learning_retry"]
    assert report["mode"] == "regenerate" and report["model_called"] is True
    assert report["outcome"] == ("completed" if updated_count else "no_updates")
    assert len(report["requested"]) == 4
    assert len(report["saved"]) == updated_count
    assert report["pending"] == report["previously_saved"] == []
    assert list(archiver.store.journal.iter_valid_entries()) == journal
    assert runtime.provider.chat_stream_with_retry.await_count == 2


async def test_missing_learning_retry_is_not_reported_as_one_saved_batch(tmp_path):
    archiver, runtime = setup(tmp_path, CHECKPOINT)
    result = await retry_session_learning(archiver, Session(key=ROUTER_SESSION_KEY), runtime, "source-missing")
    assert result["retried"] == 0
    assert result["learning_retry"]["outcome"] == "not_found"
    assert result["learning_retry"]["source"] == "source-missing"
    assert result["learning_retry"]["saved"] == []
    assert result["learning_retry"]["model_called"] is False
    runtime.provider.chat_stream_with_retry.assert_not_awaited()
