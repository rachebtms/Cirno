"""The active session stays bounded while immutable evidence and UI facts survive."""
import pytest

from cirno.config.home import get_home_path
from cirno.memory.repository import MemoryRepository
from cirno.session.display_history import HistoryFact, HistoryKind
from cirno.session.manager import SessionManager


@pytest.mark.asyncio
async def test_release_streams_evidence_and_preserves_visible_history(tmp_path):
    manager = SessionManager(tmp_path / 'workspace')
    state = manager.state
    repo = MemoryRepository(get_home_path())
    try:
        session = await state.import_messages('websocket:long', [
            {'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'record-{i} threshold=0.00003125'} for i in range(100)
        ])
        await state.append_history(session.key, [HistoryFact(HistoryKind.INPUT, {'content': 'original visible question'})], expected_generation=session.generation)
        before = await state.project_history(session.key, lambda reader: reader.turn_count)
        await state.commit_summary(session, 'checkpoint', archive_end=80)
        def archive(messages, project_id):
            # The storage owner supplies an iterator, not a decoded corpus list.
            assert not isinstance(messages, list)
            return repo.archive_messages(messages, session.key, project_id)
        assert await state.release_archived_runtime(session.key, archive) == 80
        current = await state.get(session.key)
        assert current.last_archived == 0
        assert len(current.messages) == 21
        assert current.metadata['_released_runtime_messages'] == 80
        source = current.metadata['_runtime_archive_source']
        assert repo.search('record-0', session_key=session.key, layer='source')['memories']
        assert '0.00003125' in repo.read_source(source, session_key=session.key)['lines'][0]['text']
        assert await state.project_history(session.key, lambda reader: reader.turn_count) == before
        current.add_message('user', 'next input')
        await state.finish_turn(current)
        await state.discard(current.key)
        assert (await state.get(current.key)).messages[-1]['content'] == 'next input'
    finally:
        await state.aclose()


@pytest.mark.asyncio
async def test_archive_failure_never_releases_runtime_data(tmp_path):
    state = SessionManager(tmp_path / 'workspace').state
    try:
        session = await state.import_messages('websocket:keep', [{'role':'user','content':'exact evidence'}])
        await state.commit_summary(session, 'checkpoint', archive_end=1)
        def failing_archive(*_):
            raise OSError('disk full')
        with pytest.raises(OSError, match='disk full'):
            await state.release_archived_runtime(session.key, failing_archive)
        current = await state.get(session.key)
        assert current.last_archived == 1
        assert current.messages[0]['content'] == 'exact evidence'
        assert '_released_runtime_messages' not in current.metadata
    finally:
        await state.aclose()
