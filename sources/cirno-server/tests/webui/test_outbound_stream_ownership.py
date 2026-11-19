"""Late completions cannot discard another turn's unclosed stream text."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.outbound_events import TurnEndEvent
from cirno_core.session.transport_metadata import (
    WEBSOCKET_TURN_OWNER_METADATA_KEY,
    WEBUI_TURN_METADATA_KEY,
)
from cirno_server.webui.outbound_delivery import WebUIOutboundDelivery


def delivery():
    transcripts = SimpleNamespace(
        prepare_and_append=AsyncMock(return_value=True),
        prepare_and_append_stream_event=AsyncMock(return_value=True),
    )
    output = WebUIOutboundDelivery(
        SimpleNamespace(webui_recipients=lambda _audience: ()),
        media=SimpleNamespace(), transcripts=transcripts,
        temporary_chats=SimpleNamespace(should_persist_transcript=lambda _chat: True),
        session_projection=SimpleNamespace(),
    )
    return output, transcripts


def metadata(turn, owner=None):
    return {WEBUI_TURN_METADATA_KEY: turn, **({WEBSOCKET_TURN_OWNER_METADATA_KEY: owner} if owner else {})}


async def chunk(output, mode, text, metadata, stream_id):
    method = output.send_delta if mode == 'answer' else output.send_reasoning_delta
    await method('ownership-chat', text, metadata, stream_id=stream_id)


async def end(output, mode, metadata, stream_id):
    if mode == 'answer':
        await output.send_delta('ownership-chat', '', metadata, stream_id=stream_id, stream_end=True)
    else:
        await output.send_reasoning_end('ownership-chat', metadata, stream_id=stream_id)


@pytest.mark.parametrize('mode', ['answer', 'reasoning'])
@pytest.mark.parametrize('stream_id', [None, 'shared-stream'])
async def test_interleaved_streams_keep_text_in_their_own_turn(mode, stream_id):
    output, transcripts = delivery()
    old, new = metadata('old'), metadata('new')
    await chunk(output, mode, 'Old text', old, stream_id)
    await chunk(output, mode, 'New text', new, stream_id)
    await end(output, mode, old, stream_id)
    assert transcripts.prepare_and_append_stream_event.call_args.kwargs['completed_text'] == 'Old text'
    await end(output, mode, new, stream_id)
    assert transcripts.prepare_and_append_stream_event.call_args.kwargs['completed_text'] == 'New text'


@pytest.mark.parametrize('mode', ['answer', 'reasoning'])
@pytest.mark.parametrize('old_owner,new_owner', [(None, None), ('old-owner', 'new-owner')])
async def test_old_turn_completion_preserves_a_new_stream(mode, old_owner, new_owner):
    output, transcripts = delivery()
    old, new = metadata('old', old_owner), metadata('new', new_owner)
    await chunk(output, mode, 'Old text', old, 'old-stream')
    await chunk(output, mode, 'New text', new, 'new-stream')
    await output.send(OutboundMessage(channel='websocket', chat_id='ownership-chat', content='',
                                      event=TurnEndEvent(), metadata=old))
    await end(output, mode, new, 'new-stream')
    assert transcripts.prepare_and_append_stream_event.call_args.kwargs['completed_text'] == 'New text'


async def test_owner_identity_separates_runs_that_reuse_a_wire_turn_id():
    output, transcripts = delivery()
    old, new = metadata('reused', 'old-owner'), metadata('reused', 'new-owner')
    await chunk(output, 'answer', 'Old text', old, 'same-stream')
    await chunk(output, 'answer', 'New text', new, 'same-stream')
    await output.send(OutboundMessage(channel='websocket', chat_id='ownership-chat', content='',
                                      event=TurnEndEvent(), metadata=old))
    await end(output, 'answer', new, 'same-stream')
    assert transcripts.prepare_and_append_stream_event.call_args.kwargs['completed_text'] == 'New text'


async def test_legacy_completion_and_explicit_chat_discard_still_clear_their_buffers():
    output, _ = delivery()
    await chunk(output, 'answer', 'Legacy', {}, None)
    await output.send(OutboundMessage(channel='websocket', chat_id='ownership-chat', content='', event=TurnEndEvent()))
    assert not output._stream_text_buffers
    await chunk(output, 'answer', 'One', metadata('one'), 'one')
    await chunk(output, 'reasoning', 'Two', metadata('two'), 'two')
    output.discard('ownership-chat')
    assert not output._stream_text_buffers
    assert not output._reasoning_text_buffers


@pytest.mark.parametrize('mode', ['answer', 'reasoning'])
async def test_new_stream_snapshot_reaches_durable_history_after_an_old_completion(history, mode):
    from cirno_core.session.transcript import WebUITranscriptRecorder

    output, _ = delivery()
    output._transcripts = WebUITranscriptRecorder(history.sessions)
    key = 'websocket:ownership-chat'
    history.append(key, {'event': 'user', 'text': 'Original input', 'turn_id': 'old'})
    old = await history.metadata('ownership-chat', metadata('old'))
    new = await history.metadata('ownership-chat', metadata('new'))
    await chunk(output, mode, 'Old text', old, 'old-stream')
    await chunk(output, mode, 'New durable text', new, 'new-stream')
    await output.send(OutboundMessage(channel='websocket', chat_id='ownership-chat', content='',
                                      event=TurnEndEvent(), metadata=old))
    await end(output, mode, new, 'new-stream')
    event = 'stream_end' if mode == 'answer' else 'reasoning_end'
    records = history.read(key)
    saved = next(record for record in records if record.get('event') == event and record.get('turn_id') == 'new')
    assert saved['text'] == 'New durable text'
