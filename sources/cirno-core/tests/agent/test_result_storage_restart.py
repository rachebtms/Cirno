"""A service restart after output-storage failure must not repeat completed work."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.tools.base import Tool
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.bus.queue import MessageBus
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.generation import GenerationSettings
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_core.session.recovery.contracts import RUNTIME_CHECKPOINT_KEY
from cirno_core.session.recovery.checkpoints import runtime_checkpoint_is_well_formed
from cirno_usage.types import LLMUsage


def provider(response):
    result = MagicMock(spec=LLMProvider)
    result.provider_name = "storage-test"
    result.get_default_model.return_value = "test"
    result.generation = GenerationSettings(max_tokens=1024)
    result.estimate_prompt_tokens = MagicMock(return_value=(100, "fixture"))
    result.chat_stream_with_retry = AsyncMock(return_value=response)
    result.aclose = AsyncMock()
    return result


async def test_full_turn_reopens_completed_tool_result_without_reexecuting(tmp_path, monkeypatch):
    marker = tmp_path / "measurement.csv"
    raw = "Verified sample,17,0.125\n" * 2000

    class Measurement(Tool):
        name = "record_measurement"
        description = "Record a measured sample"
        parameters = {"type": "object", "properties": {}}

        async def execute(self, **kwargs):
            with marker.open("a") as stream:
                stream.write("17,0.125\n")
            return raw

    tools = ToolRegistry()
    tools.register(Measurement())
    first_provider = provider(
        LLMResponse(
            content="Recording",
            finish_reason="tool_calls",
            tool_calls=[ToolCallRequest(id="measurement", name="record_measurement", arguments={})],
            usage=LLMUsage.reported(input_tokens=100, output_tokens=5),
        )
    )
    first = AgentLoop(
        bus=MessageBus(),
        provider=first_provider,
        workspace=tmp_path,
        model="test",
        max_tool_result_chars=2048,
    )
    key = "cli:result-recovery"
    try:
        with monkeypatch.context() as patch:

            def fail(*args, **kwargs):
                raise PermissionError("Output volume is read-only")

            patch.setattr("cirno_core.utils.tool_results._atomic_write_text", fail)
            with pytest.raises(PermissionError, match="Output volume is read-only"):
                await first.process_direct("Record the sample once", session_key=key, tools=tools)
        session = await first.sessions.state.get(key)
        checkpoint = session.metadata[RUNTIME_CHECKPOINT_KEY]
        assert runtime_checkpoint_is_well_formed(checkpoint)
        assert checkpoint["phase"] == "tools_completed"
        assert checkpoint["completed_tool_results"][0]["content"] == raw
    finally:
        await first.aclose()

    second_provider = provider(
        LLMResponse(
            content="The sample was recorded.",
            usage=LLMUsage.reported(input_tokens=100, output_tokens=5),
        )
    )
    reopened = AgentLoop(
        bus=MessageBus(),
        provider=second_provider,
        workspace=tmp_path,
        model="test",
        max_tool_result_chars=2048,
    )
    try:
        result = await reopened.process_direct("Continue", session_key=key, tools=tools)
        assert result.content == "The sample was recorded."
        assert marker.read_text() == "17,0.125\n"
        request = second_provider.chat_stream_with_retry.await_args.kwargs["messages"]
        [tool_result] = [message for message in request if message.get("role") == "tool"]
        assert "[tool output persisted]" in tool_result["content"]
        assert next((tmp_path / ".cirno/tool-results").rglob("*.txt")).read_text() == raw
        assert RUNTIME_CHECKPOINT_KEY not in (await reopened.sessions.state.get(key)).metadata
    finally:
        await reopened.aclose()
