"""Reasoning-only work remains recoverable across truncation and compaction."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.runner import AgentRunner
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.memory.consolidation import MemoryArchiver, MemoryStore
from cirno_core.memory.working_state import EvidenceCheckpoint
from cirno_core.providers.base import GenerationSettings, LLMProvider, LLMResponse
from cirno_core.providers.openai_compat_provider import OpenAICompatProvider
from cirno_core.providers.reasoning_history import prepare_reasoning_history
from cirno_core.providers.registry import find_by_name
from cirno_core.utils.helpers import estimate_prompt_tokens_chain
from cirno_core.utils.llm_runtime import LLMRuntime

from agent.runner_helpers import make_run_spec


def test_deepseek_replay_and_effective_input_count_follow_tools():
    provider = OpenAICompatProvider(api_key='fixture', default_model='deepseek-flash', spec=find_by_name('deepseek'))
    history = [{'role': 'assistant', 'content': '', 'reasoning_content': 'working state ' * 100}]
    tools = [{'type': 'function', 'function': {'name': 'inspect'}}]
    without, _ = estimate_prompt_tokens_chain(provider, 'deepseek-flash', history, [])
    with_tools, _ = estimate_prompt_tokens_chain(provider, 'deepseek-flash', history, tools)
    assert with_tools > without
    assert prepare_reasoning_history(provider, history, tools=tools)[0]['reasoning_content']
    provider.reasoning_history = 'omit'
    with pytest.raises(ValueError, match='require reasoning history'):
        prepare_reasoning_history(provider, history, tools=tools)
    assert 'reasoning_content' not in prepare_reasoning_history(provider, history)[0]
    assert history[0]['reasoning_content']


async def test_failed_summary_preserves_reasoning_only_state_and_recent_tail(tmp_path):
    store = MemoryStore(tmp_path)
    provider = MagicMock(spec=LLMProvider)
    provider.chat_stream_with_retry = AsyncMock(return_value=LLMResponse(content='(nothing)'))
    runtime = LLMRuntime(provider, 'test', GenerationSettings(max_tokens=2048), 32000)
    archiver = MemoryArchiver(store, lambda **kwargs: [], lambda _: [])
    messages = [{'role': 'user', 'content': 'Investigate calibration'}, {'role': 'assistant', 'content': '', 'reasoning_content': 'discarded intermediate ' * 4000 + '\nLATEST_STATE trial=17; next=trial18; hypothesis unverified'}]
    checkpoint = await archiver.archive(messages, runtime=runtime, session_key='test:a', history=messages, request_tools=[])
    assert isinstance(checkpoint, EvidenceCheckpoint)
    assert 'LATEST_STATE' in checkpoint and 'next=trial18' in checkpoint
    assert 'Unverified' in checkpoint or 'hypothesis unverified' in checkpoint
    call = provider.chat_stream_with_retry.call_args.kwargs
    assert call['max_tokens'] == 2048 and call['reasoning_effort'] == 'low'
    assert store.read_unprocessed_history(0)


async def test_reasoning_survives_exhausted_length_recoveries():
    provider = MagicMock(spec=LLMProvider)
    count = 0
    async def respond(**kwargs):
        nonlocal count
        count += 1
        return LLMResponse(content='', reasoning_content=f'saved state {count}', finish_reason='length')
    provider.chat_stream_with_retry = AsyncMock(side_effect=respond)
    result = await AgentRunner().run(make_run_spec(provider, model='test', initial_messages=[{'role': 'user', 'content': 'long work'}], tools=ToolRegistry(), max_iterations=4, max_tool_result_chars=16000))
    states = [message.get('reasoning_content') for message in result.messages if message.get('reasoning_content')]
    assert len(states) >= 4
    assert 'saved state 4' in states


async def test_checkpoint_reminder_is_system_origin_and_not_repeated(monkeypatch):
    from cirno_core.agent.tools.base import Tool
    from cirno_core.providers.base import ToolCallRequest
    class InspectTool(Tool):
        name = 'inspect'
        description = 'Inspect'
        parameters = {'type': 'object', 'properties': {}}
        async def execute(self, **kwargs):
            return 'verified result'
    tools = ToolRegistry()
    tools.register(InspectTool())
    provider = MagicMock(spec=LLMProvider)
    calls = []
    async def respond(**kwargs):
        calls.append(kwargs['messages'])
        return LLMResponse(content='Continue checking', tool_calls=[ToolCallRequest(id='one', name='inspect', arguments={})]) if len(calls) == 1 else LLMResponse(content='Done')
    provider.chat_stream_with_retry = AsyncMock(side_effect=respond)
    monkeypatch.setattr('cirno_core.agent.context_governance.estimate_prompt_tokens_chain', lambda *args: (8000, 'fixture'))
    await AgentRunner().run(make_run_spec(provider, model='test', context_window_tokens=11024, max_tokens=1000, initial_messages=[{'role': 'user', 'content': 'inspect'}], tools=tools, max_iterations=3, max_tool_result_chars=16000))
    reminders = [message for message in calls[-1] if message.get('_hidden_history')]
    assert len(reminders) == 1
    assert 'not a new user request' in reminders[0]['content']


async def test_deepseek_finalization_preserves_native_reasoning_context():
    from cirno_core.agent.tools.base import Tool
    from cirno_core.providers.base import ToolCallRequest

    class InspectTool(Tool):
        name = "inspect"
        description = "Inspect"
        parameters = {"type": "object", "properties": {}}

        async def execute(self, **kwargs):
            return "verified result"

    tools = ToolRegistry()
    tools.register(InspectTool())
    provider = MagicMock(spec=LLMProvider)
    provider._spec = find_by_name("deepseek")
    provider.chat_stream_with_retry = AsyncMock(side_effect=[
        LLMResponse(content="Inspecting", reasoning_content="Keep the hypothesis", tool_calls=[ToolCallRequest(id="one", name="inspect", arguments={})]),
        LLMResponse(content="Verified result is ready", reasoning_content="Compared with the hypothesis"),
    ])
    result = await AgentRunner().run(make_run_spec(provider, model="deepseek-flash", initial_messages=[{"role": "user", "content": "inspect"}], tools=tools, max_iterations=1, max_tool_result_chars=16000))
    final_request = provider.chat_stream_with_retry.call_args.kwargs
    assert final_request["tools"] == tools.get_definitions()
    assert final_request["tool_choice"] == "none"
    assert any(message.get("reasoning_content") == "Keep the hypothesis" for message in final_request["messages"])
    assert any(message.get("reasoning_content") == "Compared with the hypothesis" for message in result.messages)
    assert result.final_content == "Verified result is ready"
