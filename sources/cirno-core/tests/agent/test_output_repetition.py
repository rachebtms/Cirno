"""Repeated-output interruption is serial, bounded and separate from cancellation."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.hook import AgentHook
from cirno_core.agent.runner.engine import AgentRunner
from cirno_core.agent.runner.repetition import (
    OutputRepetitionGuard,
    RepeatedBlocks,
    RepeatedOutputDetected,
)
from cirno_core.config.repetition import OutputRepetitionConfig
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_core.session.recovery.checkpoints import runtime_checkpoint_is_well_formed
from pydantic import ValidationError

from sources.development.testing.runtime import make_run_spec


@pytest.mark.parametrize('chunks', [list('停住。\n'*4), ['停住。\n'*4], ['停住。', '\n停住。\n', '停住。\n停住。']])
def test_chunk_boundaries_do_not_change_detection(chunks):
    blocks = RepeatedBlocks(4)
    assert any(blocks.feed(chunk) for chunk in chunks)


def test_prose_not_arbitrary_repeated_code_or_single_characters():
    blocks = RepeatedBlocks(4)
    assert not blocks.feed('```python\n' + 'print("same.")\n'*100 + '```\n')
    assert not blocks.feed('a.\n'*100)
    assert not blocks.feed('One sentence. Two sentences. Three sentences. Four sentences.', final=True)
    assert blocks.feed('1. Stop now!\n2. Stop now!\n3. Stop now!\n4. Stop now!')


def test_tail_history_and_new_user_input():
    history = [{'role':'user','content':'work'}, *[{'role':'assistant','content':'停住。'} for _ in range(3)]]
    history += [{'role':'user','content':'continue', '_hidden_history':{'kind':'goal_continuation'}}]
    with pytest.raises(RepeatedOutputDetected):
        OutputRepetitionGuard(OutputRepetitionConfig(), history).check('停住。')
    history.append({'role':'user','content':'Say 停住 once'})
    OutputRepetitionGuard(OutputRepetitionConfig(), history).check('停住。')


@pytest.mark.parametrize('values', [{'repeat_count':2}, {'max_interventions':0}, {'guidance':'  '}])
def test_invalid_settings_are_rejected(values):
    with pytest.raises(ValidationError):
        OutputRepetitionConfig(**values)


def fixture_spec(respond, *, streaming=True, **overrides):
    provider = MagicMock(spec=LLMProvider)
    provider.chat_stream_with_retry = AsyncMock(side_effect=respond)
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value='sent')
    hook = AgentHook()
    hook.wants_streaming = MagicMock(return_value=streaming)
    hook.on_stream = AsyncMock()
    hook.emit_reasoning = AsyncMock()
    spec = make_run_spec(provider, tools=tools, model='fixture', max_iterations=8,
                         max_tool_result_chars=16000, hook=hook,
                         initial_messages=[{'role':'system','content':'stable prefix'}, {'role':'user','content':'work'}],
                         **overrides)
    return spec, provider, tools, hook


@pytest.mark.parametrize('channel', ['content', 'thinking', 'tool', 'nonstream', 'snapshot'])
async def test_interrupts_before_repeated_chunk_or_tool_delivery_and_guides_serially(channel):
    requests, closed = [], []
    checkpoints = []
    async def respond(**kwargs):
        requests.append(deepcopy(kwargs['messages']))
        if len(requests) == 1:
            try:
                if channel in {'content', 'thinking'}:
                    await kwargs['on_'+('content' if channel=='content' else 'thinking')+'_delta']('停住。\n'*50)
                    pytest.fail('repeated stream did not interrupt')
                if channel == 'snapshot':
                    await kwargs['on_content_delta']('Starting work. ')
                    return LLMResponse(content='Starting work. '+ '停住。'*50)
                if channel == 'tool':
                    return LLMResponse(content='', tool_calls=[ToolCallRequest('reply','user__message',{'content':'停住。\n'*50})], finish_reason='tool_calls')
                return LLMResponse(content='停住。\n'*50)
            finally:
                closed.append(True)
        assert closed == [True]  # Old stream closed before correction starts.
        return LLMResponse(content='I have paused my task and saved progress.')
    async def checkpoint(payload):
        checkpoints.append(payload)
    config = OutputRepetitionConfig(guidance='Review the stop instruction and pause your Goal.')
    spec, provider, tools, hook = fixture_spec(respond, streaming=channel!='nonstream', output_repetition=config, checkpoint_callback=checkpoint)
    result = await AgentRunner().run(spec)
    assert result.stop_reason == 'completed'
    assert provider.chat_stream_with_retry.await_count == 2
    assert requests[1][:2] == requests[0][:2]
    assert requests[1][-1]['content'].endswith(config.guidance)
    assert requests[1][-1].get('_hidden_history', {}).get('kind') == 'repetition_guidance'
    assert all(runtime_checkpoint_is_well_formed(row) for row in checkpoints)
    assert not any('停住' in call.args[-1] for call in hook.on_stream.await_args_list)
    assert not any('停住' in call.args[0] for call in hook.emit_reasoning.await_args_list)
    tools.execute.assert_not_called()
    assert not asyncio.current_task().cancelling()


async def test_repeated_corrections_stop_at_limit_instead_of_looping():
    async def respond(**kwargs):
        await kwargs['on_content_delta']('停住。'*10)
        raise AssertionError('not interrupted')
    spec, provider, _, _ = fixture_spec(respond)
    result = await AgentRunner().run(spec)
    assert provider.chat_stream_with_retry.await_count == 3
    assert result.stop_reason == 'repetition_limit'
    assert 'paused' in result.final_content
    assert sum(row.get('_hidden_history',{}).get('kind')=='repetition_guidance' for row in result.messages) == 2


async def test_disabled_guard_and_real_task_cancellation():
    async def respond(**kwargs):
        await kwargs['on_content_delta']('停住。'*10)
        return LLMResponse(content='停住。'*10)
    spec, provider, _, _ = fixture_spec(respond, output_repetition=OutputRepetitionConfig(enabled=False))
    assert (await AgentRunner().run(spec)).final_content == '停住。'*10
    assert provider.chat_stream_with_retry.await_count == 1
    provider.chat_stream_with_retry.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await AgentRunner().run(spec)


async def test_max_iteration_finalization_also_rejects_repetition():
    async def respond(**kwargs):
        if kwargs.get('tools') is not None:
            return LLMResponse(content='Working', tool_calls=[ToolCallRequest('read','list_dir',{'path':'.'})], finish_reason='tool_calls')
        await kwargs['on_content_delta']('停住。'*10)
        raise AssertionError('finalization stream was not interrupted')
    spec, provider, _, _ = fixture_spec(respond)
    spec.max_iterations = 1
    spec.tools.get_definitions.return_value = [{'type':'function', 'function':{'name':'list_dir','parameters':{}}}]
    result = await AgentRunner().run(spec)
    assert provider.chat_stream_with_retry.await_count == 2
    assert result.stop_reason == 'repetition_limit'
    assert '停住' not in result.final_content


@pytest.mark.parametrize('status', ['active', 'waiting'])
async def test_guard_persists_pause_progress_and_notifies_router(tmp_path, status):
    from cirno_core.agent.goals.scheduler import wake_due_goals
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.agent.tools.registry import ToolRegistry
    from cirno_core.bus.queue import MessageBus
    from cirno_core.config.home import set_instance_path
    from cirno_core.session.keys import ROUTER_SESSION_KEY

    set_instance_path(tmp_path)
    provider = MagicMock(spec=LLMProvider)
    provider.get_default_model.return_value = 'fixture'
    provider.provider_name = 'fixture'
    provider.chat_stream_with_retry = AsyncMock(return_value=LLMResponse(content='停住。'*12))
    bus = MessageBus()
    loop = AgentLoop(bus=bus, provider=provider, model='fixture', workspace=tmp_path/'workspace',
                     tool_registry=ToolRegistry(), output_repetition=OutputRepetitionConfig(max_interventions=1))
    key = 'websocket:worker'
    try:
        await loop.sessions.state.get(key)
        await loop.sessions.state.get(ROUTER_SESSION_KEY)
        await loop.sessions.state.update_metadata(key, {
            'delegated_by':ROUTER_SESSION_KEY,
            'goal_state':{'goal_id':'existing-task','status':status,'objective':'Wait for a new user instruction',
                          'recap':'Verified progress remains saved','report_to':ROUTER_SESSION_KEY,
                          'wake_at':'2000-01-01T00:00:00+00:00'},
        })
        result = await loop.process_direct('No more work until I ask', session_key=key, channel='websocket', chat_id='worker')
        assert result is not None and 'paused' in result.content
        stored = await loop.sessions.state.read(key)
        assert stored.metadata['goal_state']['status'] == 'paused'
        assert 'wake_at' not in stored.metadata['goal_state']
        assert stored.metadata['goal_state']['recap'] == 'Verified progress remains saved'
        assert stored.metadata['goal_state']['goal_id'] == 'existing-task'
        assert stored.metadata['work_report']['state'] == 'blocked'
        assert stored.metadata['work_report']['execution']['stop_reason'] == 'repetition_limit'
        assert any(row.get('_hidden_history',{}).get('kind')=='repetition_guidance' for row in stored.messages)
        count = provider.chat_stream_with_retry.await_count
        await wake_due_goals(loop)
        assert provider.chat_stream_with_retry.await_count == count
    finally:
        await loop.aclose()
        set_instance_path(None)


async def test_automatic_continuation_keeps_repetition_state_but_genuine_input_resets_it(tmp_path):
    from cirno_core.agent.context import ContextBuilder, TranscriptInput
    from cirno_core.agent.runner.inputs import build_continuation_message
    history = [{'role':'user','content':'work'}, *[{'role':'assistant','content':'停住。'} for _ in range(3)]]
    config = OutputRepetitionConfig()
    builder = ContextBuilder(tmp_path)
    transcript = TranscriptInput(history, 'Continue the Goal', current_message_internal=True)
    messages = builder.build_transcript(transcript, session_key='websocket:worker')
    with pytest.raises(RepeatedOutputDetected):
        OutputRepetitionGuard(config, messages).check('停住。')
    spec, _, _, _ = fixture_spec(AsyncMock())
    spec.continuation_callback = AsyncMock(return_value='Continue the Goal')
    continuation = await build_continuation_message(spec)
    with pytest.raises(RepeatedOutputDetected):
        OutputRepetitionGuard(config, [*history, continuation]).check('停住。')
    guard = OutputRepetitionGuard(config, [])
    notices = [guard.guidance_message(), guard.guidance_message()]
    assert OutputRepetitionGuard(config, [*history, *notices, continuation]).interventions == 2
    assert OutputRepetitionGuard(config, [*history, *notices, {'role':'user','content':'A new request'}]).interventions == 0


async def test_identical_answers_across_automatic_goal_segments_trigger_guidance():
    continuing = True
    requests = []
    async def respond(**kwargs):
        nonlocal continuing
        requests.append(deepcopy(kwargs['messages']))
        if requests[-1][-1].get('_hidden_history',{}).get('kind') == 'repetition_guidance':
            continuing = False
            return LLMResponse(content='Progress is saved; the task is paused.')
        return LLMResponse(content='停住。')
    async def continuation():
        return 'Continue the active Goal' if continuing else None
    spec, provider, _, _ = fixture_spec(respond, streaming=False, continuation_callback=continuation)
    result = await AgentRunner().run(spec)
    assert result.stop_reason == 'completed'
    assert result.final_content == 'Progress is saved; the task is paused.'
    assert provider.chat_stream_with_retry.await_count == 5
    assert sum(row.get('_hidden_history',{}).get('kind')=='repetition_guidance' for row in result.messages) == 1


def test_history_seeding_uses_the_actual_tail_even_after_an_old_repetition():
    history = [{'role':'assistant', 'content':'停住。'*10+' A different ending.'}]
    OutputRepetitionGuard(OutputRepetitionConfig(), history).check('停住。')


async def test_live_display_disabled_still_interrupts_the_provider_stream():
    requests = 0
    async def respond(**kwargs):
        nonlocal requests
        requests += 1
        if requests == 1:
            await kwargs['on_content_delta']('停住。'*50)
            pytest.fail('non-displayed stream was not interrupted')
        return LLMResponse(content='A useful new answer.')
    spec, provider, _, hook = fixture_spec(respond, streaming=False)
    result = await AgentRunner().run(spec)
    assert result.final_content == 'A useful new answer.'
    assert provider.chat_stream_with_retry.await_count == 2
    hook.on_stream.assert_not_called()
