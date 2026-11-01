import asyncio
import json

import pytest
from cirno.agent.tools.ask_user import AskUserTool
from cirno.agent.tools.context import RequestContext, request_context
from cirno.agent.tools.message import capture_message_deliveries, current_conversation_has_delivery
from cirno.bus.events import OUTBOUND_META_AGENT_UI


@pytest.mark.asyncio
async def test_question_returns_without_user_reply_and_is_bound_to_current_chat():
    sent = []
    async def send(message):
        sent.append(message)
    tool = AskUserTool(send_callback=send)
    with request_context(RequestContext(channel='websocket', chat_id='one', session_key='websocket:one',
                                        session_generation='generation', metadata={'webui_turn_id': 'turn-one'})):
        with capture_message_deliveries():
            result = json.loads(await asyncio.wait_for(tool.execute(
                question='Which format?', options=['CSV', 'JSON'], assumption='I will inspect the files first.',
                chat_id='another-chat',
            ), timeout=0.2))
            assert not current_conversation_has_delivery()  # a question must not suppress the final reply
    assert result['status'] == 'posted'
    assert len(sent) == 1
    message = sent[0]
    assert message.chat_id == 'one'
    assert message.metadata['_session_generation'] == 'generation'
    assert message.metadata['webui_turn_id'] == 'turn-one'
    question = message.metadata[OUTBOUND_META_AGENT_UI]
    assert question['kind'] == 'user_question'
    assert question['data']['id'] == result['question_id']
    assert question['data']['options'] == ['CSV', 'JSON']
    assert 'CSV' in message.content  # text-only channels have a readable fallback


@pytest.mark.asyncio
async def test_failed_delivery_is_not_reported_as_posted():
    async def send(_message):
        raise RuntimeError('offline')
    tool = AskUserTool(send_callback=send, default_channel='websocket', default_chat_id='one')
    result = await tool.execute('Which format?')
    assert result.is_error and 'offline' in result


@pytest.mark.asyncio
@pytest.mark.parametrize('values', [{'question': ''}, {'question': 'q', 'options': ['']},
                                   {'question': 'q', 'options': ['x'] * 7}, {'question': 'q', 'assumption': 'x' * 1001}])
async def test_rejects_invalid_questions(values):
    assert (await AskUserTool().execute(**values)).is_error


@pytest.mark.asyncio
async def test_batch_posts_in_order_without_waiting_for_answers():
    sent = []
    async def send(message):
        sent.append(message)
    tool = AskUserTool(send_callback=send, default_channel='websocket', default_chat_id='one')
    result = json.loads(await asyncio.wait_for(tool.execute(questions=[
        {'question': 'First?', 'options': [' CSV ', 'CSV', 'JSON']},
        {'question': 'Second?', 'assumption': 'Continue checking files.'},
    ]), timeout=0.2))
    data = [message.metadata[OUTBOUND_META_AGENT_UI]['data'] for message in sent]
    assert [row['question'] for row in data] == ['First?', 'Second?']
    assert data[0]['options'] == ['CSV', 'JSON']
    assert result['count'] == 2
    assert result['question_ids'] == [row['id'] for row in data]
    assert len(set(result['question_ids'])) == 2
    assert all(message.chat_id == 'one' for message in sent)


@pytest.mark.asyncio
@pytest.mark.parametrize('values', [
    {'questions': []}, {'questions': [{'question': 'q'}] * 9},
    {'questions': [{'question': 'Valid?'}, {'question': ''}]},
    {'questions': [{'question': 'q', 'unknown': True}]},
    {'questions': [{'question': 'q'}], 'question': 'single'},
])
async def test_invalid_batch_does_not_post_any_question(values):
    sent = []
    async def send(message):
        sent.append(message)
    tool = AskUserTool(send_callback=send, default_channel='websocket', default_chat_id='one')
    assert (await tool.execute(**values)).is_error
    assert not sent


@pytest.mark.asyncio
async def test_partial_delivery_reports_posted_ids_so_retries_do_not_duplicate_them():
    sent = []
    async def send(message):
        if sent:
            raise RuntimeError('offline')
        sent.append(message)
    tool = AskUserTool(send_callback=send, default_channel='websocket', default_chat_id='one')
    result = await tool.execute(questions=[{'question': 'First?'}, {'question': 'Second?'}])
    assert result.is_error
    payload = json.loads(result)
    assert payload['status'] == 'partial'
    assert payload['posted_question_ids'] == [sent[0].metadata[OUTBOUND_META_AGENT_UI]['data']['id']]
    assert payload['failed_index'] == 2
    assert 'offline' in payload['error']
