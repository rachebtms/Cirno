"""Tests for tool result persistence: large results, retained evidence and replay."""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.governance.messages import prepare_messages
from cirno_core.agent.governance.results import normalize_tool_result
from cirno_core.config.agents import AgentDefaults
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_usage.types import LLMUsage

from sources.development.testing.runtime import make_run_spec

_MAX_TOOL_RESULT_CHARS = AgentDefaults().max_tool_result_chars


@pytest.mark.parametrize("invalid_block", [42, ["nested"], {}, {"type": "text", "text": 42}])
def test_unrecognized_result_list_is_not_partially_offloaded(tmp_path, invalid_block):
    from cirno_core.agent.governance import ContextGovernanceConfig
    from cirno_core.agent.tools.registry import ToolRegistry

    result = [{"type": "text", "text": "x" * 20_000}, invalid_block]
    config = ContextGovernanceConfig(
        provider=MagicMock(), model="test", tools=ToolRegistry(), workspace=tmp_path,
        session_key="invalid", max_tool_result_chars=2048,
    )
    assert normalize_tool_result(config, "call", "custom", result) is result
    assert list(tmp_path.iterdir()) == []


async def test_runner_persists_large_tool_results_for_follow_up_calls(tmp_path):
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.agent.runner.engine import AgentRunner
    from cirno_core.session.model import Session

    provider = MagicMock()
    captured_second_call: list[dict] = []
    call_count = {"n": 0}

    async def chat_stream_with_retry(*, messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LLMResponse(
                content="working",
                tool_calls=[ToolCallRequest(id="call_big", name="list_dir", arguments={"path": "."})],
                usage=LLMUsage.reported(input_tokens=5, output_tokens=3),
            )
        captured_second_call[:] = messages
        return LLMResponse(content="done", tool_calls=[], usage=None)

    provider.chat_stream_with_retry = chat_stream_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="x" * 20_000)

    runner = AgentRunner()
    result = await runner.run(make_run_spec(provider,
        initial_messages=[{"role": "user", "content": "do task"}],
        tools=tools,
        model="test-model",
        max_iterations=2,
        workspace=tmp_path,
        session_key="test:runner",
        max_tool_result_chars=2048,
    ))

    assert result.final_content == "done"
    tool_message = next(msg for msg in captured_second_call if msg.get("role") == "tool")
    assert len(tool_message["content"]) <= 2048
    assert "[tool output persisted]" in tool_message["content"]
    assert "Result truncated. Read the saved file" in tool_message["content"]
    assert "tool-results" in tool_message["content"]
    persisted_path = next((tmp_path / ".cirno/tool-results/test_runner").glob("*.txt"))
    assert persisted_path.read_text(encoding="utf-8") == "x" * 20_000

    from cirno_core.agent.tools.filesystem import ReadFileTool

    readback = await ReadFileTool(workspace=tmp_path).execute(
        path=str(persisted_path)
    )
    assert "x" * 20_000 in readback

    loop = AgentLoop.__new__(AgentLoop)
    from cirno_core.agent.execution.persistence import TurnPersistence
    loop.persistence = TurnPersistence(loop)
    loop.max_tool_result_chars = 2048
    session = Session(key="test:runner")
    loop.persistence.save_messages(session, result.messages, skip=1)
    persisted_tool = next(message for message in session.messages if message.get("role") == "tool")
    assert persisted_tool["content"] == tool_message["content"]

    replay_provider = MagicMock()
    replay_provider.chat_stream_with_retry = AsyncMock(
        return_value=LLMResponse(content="replayed", tool_calls=[], usage=None)
    )
    replay_tools = MagicMock()
    replay_tools.get_definitions.return_value = []
    replay_result = await AgentRunner().run(make_run_spec(replay_provider,
        initial_messages=[
            *session.get_history(),
            {"role": "user", "content": "continue"},
        ],
        tools=replay_tools,
        model="test-model",
        max_iterations=1,
        workspace=tmp_path,
        session_key="test:runner",
        max_tool_result_chars=2048,
    ))
    replay_tool = next(
        message
        for message in replay_provider.chat_stream_with_retry.await_args.kwargs["messages"]
        if message.get("role") == "tool"
    )
    assert replay_result.final_content == "replayed"
    assert replay_tool["content"] == tool_message["content"]


def test_persist_tool_result_retains_old_referenced_session_buckets(tmp_path):
    from cirno_core.utils.tool_results import maybe_persist_tool_result

    root = tmp_path / ".cirno" / "tool-results"
    old_bucket = root / "old_session"
    recent_bucket = root / "recent_session"
    old_bucket.mkdir(parents=True)
    recent_bucket.mkdir(parents=True)
    (old_bucket / "old.txt").write_text("old", encoding="utf-8")
    (recent_bucket / "recent.txt").write_text("recent", encoding="utf-8")

    retained = []
    for index in range(40):
        evidence = root / f"research_{index}" / "result.txt"
        evidence.parent.mkdir()
        evidence.write_text(f"evidence {index}")
        retained.append(evidence)

    stale = time.time() - (8 * 24 * 60 * 60)
    os.utime(old_bucket, (stale, stale))
    os.utime(old_bucket / "old.txt", (stale, stale))

    persisted = maybe_persist_tool_result(
        tmp_path,
        "current:session",
        "call_big",
        "x" * 5000,
        max_chars=64,
    )

    assert "truncated" in persisted
    assert ".cirno" in persisted
    assert (old_bucket / "old.txt").read_text() == "old"
    assert recent_bucket.exists()
    assert [path.read_text() for path in retained] == [f"evidence {index}" for index in range(40)]
    assert len(list((root / "current_session").glob("*.txt"))) == 1


def test_persist_tool_result_leaves_no_temp_files(tmp_path):
    from cirno_core.utils.tool_results import maybe_persist_tool_result

    root = tmp_path / ".cirno" / "tool-results"
    maybe_persist_tool_result(
        tmp_path,
        "current:session",
        "call_big",
        "x" * 5000,
        max_chars=64,
    )

    assert len(list((root / "current_session").glob("*.txt"))) == 1
    assert list((root / "current_session").glob("*.tmp")) == []




async def test_read_file_result_is_not_offloaded(tmp_path):
    """read_file must not trigger generic offloading (prevents persist->read->persist loops)."""
    from cirno_core.agent.runner.engine import AgentRunner

    provider = MagicMock()
    captured_second_call: list[dict] = []
    call_count = {"n": 0}

    async def chat_stream_with_retry(*, messages, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LLMResponse(
                content="reading",
                tool_calls=[ToolCallRequest(id="call_rf", name="read_file", arguments={"path": "big.txt"})],
                usage=LLMUsage.reported(input_tokens=5, output_tokens=3),
            )
        captured_second_call[:] = messages
        return LLMResponse(content="done", tool_calls=[], usage=None)

    provider.chat_stream_with_retry = chat_stream_with_retry
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="x" * 20_000)

    runner = AgentRunner()
    result = await runner.run(make_run_spec(provider,
        initial_messages=[{"role": "user", "content": "read big file"}],
        tools=tools,
        model="test-model",
        max_iterations=2,
        workspace=tmp_path,
        session_key="test:runner",
        max_tool_result_chars=2048,
    ))

    assert result.final_content == "done"
    tool_message = next(msg for msg in captured_second_call if msg.get("role") == "tool")
    # read_file result must NOT be offloaded to a file
    assert "[tool output persisted]" not in tool_message["content"]
    # read_file manages its own size; generic truncation must NOT apply
    assert len(tool_message["content"]) == 20_000
    # no file should have been written for this read_file call
    offload_dir = tmp_path / ".cirno" / "tool-results"
    assert not any(offload_dir.rglob("call_rf.txt")) if offload_dir.exists() else True


async def test_processed_tool_result_is_stable_for_persistence_and_replay(tmp_path):
    """The content sent after a tool call must survive the session round trip unchanged."""
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.agent.runner.engine import AgentRunner
    from cirno_core.session.model import Session

    raw_result = "start-" + ("x" * 20_000) + "-end-marker"
    first_provider = MagicMock()
    first_tools = MagicMock()
    first_tools.get_definitions.return_value = []
    first_tools.execute = AsyncMock(return_value=raw_result)

    first_provider.chat_stream_with_retry = AsyncMock(side_effect=[
        LLMResponse(
            content="working",
            tool_calls=[ToolCallRequest(
                id="call_replay",
                name="read_file",
                arguments={"path": "large.txt"},
            )],
            usage=None,
        ),
        LLMResponse(content="done", tool_calls=[], usage=None),
    ])
    result = await AgentRunner().run(make_run_spec(first_provider,
        initial_messages=[{"role": "user", "content": "read large file"}],
        tools=first_tools,
        model="test-model",
        max_iterations=2,
        workspace=tmp_path,
        session_key="test:replay",
        max_tool_result_chars=2048,
    ))
    request_tool = next(
        message for message in first_provider.chat_stream_with_retry.await_args_list[1].kwargs["messages"]
        if message.get("role") == "tool"
    )

    loop = AgentLoop.__new__(AgentLoop)
    from cirno_core.agent.execution.persistence import TurnPersistence
    loop.persistence = TurnPersistence(loop)
    loop.max_tool_result_chars = 2048
    session = Session(key="test:replay")
    loop.persistence.save_messages(session, result.messages, skip=1)
    persisted_tool = next(message for message in session.messages if message.get("role") == "tool")

    assert request_tool["content"] == raw_result
    assert persisted_tool["content"] == request_tool["content"]

    replay_provider = MagicMock()
    replay_provider.chat_stream_with_retry = AsyncMock(
        return_value=LLMResponse(content="replayed", tool_calls=[], usage=None)
    )
    replay_tools = MagicMock()
    replay_tools.get_definitions.return_value = []
    replay_result = await AgentRunner().run(make_run_spec(replay_provider,
        initial_messages=[
            *session.get_history(),
            {"role": "user", "content": "continue"},
        ],
        tools=replay_tools,
        model="test-model",
        max_iterations=1,
        workspace=tmp_path,
        session_key="test:replay",
        max_tool_result_chars=2048,
    ))
    replay_request_tool = next(
        message for message in replay_provider.chat_stream_with_retry.await_args.kwargs["messages"]
        if message.get("role") == "tool"
    )

    assert replay_result.final_content == "replayed"
    assert replay_request_tool["content"] == request_tool["content"]




async def test_mixed_tool_text_survives_model_save_replay(tmp_path):
    from cirno_core.agent.governance import ContextGovernanceConfig
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.agent.tools.filesystem import ReadFileTool
    from cirno_core.agent.tools.registry import ToolRegistry
    from cirno_core.session.model import Session

    tools = ToolRegistry()
    reader = ReadFileTool(workspace=tmp_path, allowed_dir=tmp_path)
    tools.register(reader)
    config = ContextGovernanceConfig(
        provider=MagicMock(), model="test", tools=tools, workspace=tmp_path,
        session_key="mixed", max_tool_result_chars=2048,
    )
    raw = "start-" + "x" * 20_000 + "-end"
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}}
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [{
            "id": "mixed", "type": "function",
            "function": {"name": "custom_image_tool", "arguments": "{}"},
        }]},
        {"role": "tool", "name": "custom_image_tool", "tool_call_id": "mixed",
         "content": [{"type": "text", "text": raw}, image]},
    ]
    live = prepare_messages(config, messages)
    reference = live[-1]["content"][0]["text"]
    assert len(reference) <= 2048
    assert live[-1]["content"][1] == image
    loop = AgentLoop.__new__(AgentLoop)
    from cirno_core.agent.execution.persistence import TurnPersistence
    loop.persistence = TurnPersistence(loop)
    session = Session(key="mixed")
    loop.persistence.save_messages(session, live, skip=0)
    replay = prepare_messages(config, session.get_history())
    assert replay[-1]["content"][0]["text"] == reference
    assert "data:image" not in str(replay[-1]["content"])
    readback = await reader.execute(path=str(next((tmp_path / ".cirno/tool-results/mixed").glob("*.txt"))))
    assert raw in readback
    assert messages[-1]["content"][0]["text"] == raw


async def test_tiny_budget_keeps_complete_readable_reference(tmp_path):
    from cirno_core.agent.governance import ContextGovernanceConfig
    from cirno_core.agent.tools.filesystem import ReadFileTool
    from cirno_core.agent.tools.registry import ToolRegistry

    tools = ToolRegistry()
    reader = ReadFileTool(workspace=tmp_path, allowed_dir=tmp_path)
    tools.register(reader)
    session_key = "review-session-0123456789-0123456789"
    call_id = "call_012345678901234567890123456789"
    config = ContextGovernanceConfig(
        provider=MagicMock(), model="test", tools=tools, workspace=tmp_path,
        session_key=session_key, max_tool_result_chars=64,
    )
    raw = "y" * 20_000
    reference = normalize_tool_result(config, call_id, "exec", raw)
    assert reference.startswith("[truncated: ") and reference.endswith("]")
    path = reference.removeprefix("[truncated: ").removesuffix("]")
    assert raw in await reader.execute(path=path)
    assert normalize_tool_result(config, call_id, "exec", reference) == reference
    assert (tmp_path / path).read_text(encoding="utf-8") == raw


async def test_result_reference_survives_workspace_switch_without_bypassing_restriction(tmp_path):
    import re

    from cirno_core.agent.tools.filesystem import ReadFileTool
    from cirno_core.security.workspace_access import (
        bind_workspace_scope,
        build_workspace_scope,
        reset_workspace_scope,
    )
    from cirno_core.utils.tool_results import maybe_persist_tool_result

    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    raw = "x" * 20_000
    reference = maybe_persist_tool_result(first, "session", "call", raw, max_chars=2048)
    match = re.search(r"workspace path: (.+)", reference)
    assert match is not None
    reader = ReadFileTool(workspace=first)
    for mode, expected in [("full", raw), ("restricted", "Error")]:
        token = bind_workspace_scope(build_workspace_scope(second, mode))
        try:
            result = await reader.execute(path=match[1], force=True)
            assert expected in result
        finally:
            reset_workspace_scope(token)


@pytest.mark.parametrize("budget", [2048, 16000])
def test_offload_preview_uses_budget_and_retains_tail(tmp_path, budget):
    from cirno_core.utils.tool_results import maybe_persist_tool_result

    content = "FIRST MATCH\n" + "x" * 20000 + "\n(use offset=250 to continue)"
    result = maybe_persist_tool_result(tmp_path, "search", "call", content, max_chars=budget)

    assert budget - 10 <= len(result) <= budget
    assert "FIRST MATCH" in result
    assert "use offset=250 to continue" in result
    assert "Read the saved file" in result
    assert next((tmp_path / ".cirno/tool-results/search").glob("*.txt")).read_text(encoding="utf-8") == content


async def test_grep_page_survives_default_result_normalization(tmp_path):
    from cirno_core.agent.governance import ContextGovernanceConfig
    from cirno_core.agent.tools.registry import ToolRegistry
    from cirno_core.agent.tools.search import GrepTool

    (tmp_path / "source.txt").write_text(
        "\n".join(f"needle {n} " + "x" * 100 for n in range(200)), encoding="utf-8",
    )
    page = await GrepTool(workspace=tmp_path).execute(pattern="needle", head_limit=0)
    config = ContextGovernanceConfig(
        provider=MagicMock(), model="test", tools=ToolRegistry(), workspace=tmp_path,
        session_key="search", max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
    )
    normalized = normalize_tool_result(config, "call", "grep", page)

    assert "use offset=" in normalized
    assert len(normalized) <= _MAX_TOOL_RESULT_CHARS
    assert normalized == page
    assert not (tmp_path / ".cirno/tool-results").exists()
