"""Receipt correctness, scoped recall, split-store migration and chunk coverage."""

import pytest

from cirno.memory.repository import MemoryRepository


def event(repo, text="Recorded value 0.00003125", **kwargs):
    return repo.save(text, source="test:original", session_key="a", **kwargs)


def test_normal_response_without_receipts_never_consumes_inputs(tmp_path):
    repo = MemoryRepository(tmp_path)
    event(repo)
    token, _ = repo.pending()
    report = repo.finish(token)
    assert report["retained"] == 1
    assert "per-input confirmation" in repo.status()["failures"][0]["error"]


def test_partial_receipts_settle_only_verified_inputs(tmp_path):
    repo = MemoryRepository(tmp_path)
    first, second, third, fourth = [event(repo, str(i)) for i in range(4)]
    token, _ = repo.pending()
    knowledge = event(repo, "Grounded result", layer="knowledge", based_on=first['id'], enqueue=False)
    repo.confirm(token, first['id'], 1, 'created', [knowledge['id']], 'Saved grounded knowledge', session_key='a')
    repo.confirm(token, second['id'], 1, 'skipped', reason='Temporary greeting only', session_key='a')
    repo.confirm(token, third['id'], 1, 'failed', reason='Original experiment result unavailable', session_key='a')
    result = repo.finish(token)
    assert result == dict(created=1, merged=0, skipped=1, failed=2, retained=2)
    assert {r['memory_id'] for r in repo.status()['failures']} == {third['id'], fourth['id']}
    assert len(MemoryRepository(tmp_path).receipts()['receipts']) == 3


def test_confirmation_rejects_ungrounded_or_invisible_targets(tmp_path):
    repo = MemoryRepository(tmp_path)
    original = event(repo)
    unrelated = event(repo, 'Unrelated', layer='knowledge', enqueue=False)
    private = repo.save('Other project secret', source='test:private', session_key='b', layer='knowledge', enqueue=False)
    token, _ = repo.pending()
    with pytest.raises(ValueError, match='cite'):
        repo.confirm(token, original['id'], 1, 'merged', [unrelated['id']], 'Not grounded', session_key='a')
    with pytest.raises(PermissionError):
        repo.confirm(token, original['id'], 1, 'merged', [private['id']], 'Outside scope', session_key='a')
    repo.link(unrelated['id'], original['id'], 'supports', 'Original supports this existing finding', session_key='a')
    repo.confirm(token, original['id'], 1, 'merged', [unrelated['id']], 'Added corroborating evidence', session_key='a')
    assert repo.finish(token)['merged'] == 1


def test_changed_input_cannot_be_confirmed_or_lost(tmp_path):
    repo = MemoryRepository(tmp_path)
    original = event(repo)
    token, _ = repo.pending()
    event(repo, 'Corrected input', memory_id=original['id'], expected_revision=1)
    with pytest.raises(ValueError, match='changed'):
        repo.confirm(token, original['id'], 1, 'skipped', reason='Wrong old revision', session_key='a')
    assert repo.finish(token)['retained'] == 1
    assert repo.pending()[1][0]['revision'] == 2


def test_confirmed_target_missing_from_disk_keeps_input_queued(tmp_path):
    repo = MemoryRepository(tmp_path)
    original = event(repo)
    token, _ = repo.pending()
    knowledge = event(repo, 'Result', layer='knowledge', based_on=original['id'], enqueue=False)
    repo.confirm(token, original['id'], 1, 'created', [knowledge['id']], 'Saved', session_key='a')
    (tmp_path / knowledge['path']).unlink()
    assert repo.finish(token)['retained'] == 1


def test_knowledge_and_evidence_recall_are_separate(tmp_path):
    repo = MemoryRepository(tmp_path)
    raw = event(repo, 'Temperature 25.125')
    learned = event(repo, 'Temperature 25.125', layer='knowledge')
    assert [r['id'] for r in repo.search('Temperature', purpose='knowledge')['memories']] == []
    assert [r['id'] for r in repo.search('Temperature', purpose='knowledge', session_key='a')['memories']] == [learned['id']]
    assert [r['id'] for r in repo.search('Temperature', purpose='evidence', session_key='a')['memories']] == [raw['id']]


def test_event_time_is_not_modification_time_and_end_date_is_inclusive(tmp_path):
    repo = MemoryRepository(tmp_path)
    old = event(repo, 'Calibration', observed_at='2024-02-29T23:59:59+08:00')
    event(repo, 'Calibration date unknown')
    event(repo, 'Calibration later', observed_at='2025-01-01T00:00:00Z')
    found = repo.search('Calibration', session_key='a', since='2024-02-29', until='2024-02-29')
    assert [r['id'] for r in found['memories']] == [old['id']]
    assert not repo.search('Calibration', session_key='a', since='2024-02-29', until='2024-02-29', time_field='updated_at')['memories']
    with pytest.raises(ValueError):
        repo.search('Calibration', since='not-a-date')


def test_tags_and_neighbors_are_bounded_and_scope_checked(tmp_path):
    repo = MemoryRepository(tmp_path)
    first = event(repo, 'Old finding', tags=['common'], layer='knowledge')
    newer = event(repo, 'New finding', tags=['common', 'correction'], layer='knowledge')
    repo.link(newer['id'], first['id'], 'supersedes', 'New evidence', session_key='a')
    hidden = repo.save('Secret', source='test:private', session_key='b', tags=['secret'], layer='knowledge')
    with repo.connect() as db:
        db.execute('INSERT INTO links VALUES(?,?,?,?)', (newer['id'], hidden['id'], 'related', 'admin link'))
    tags = repo.list_tags(session_key='a')['tags']
    assert tags == [{'name': 'common', 'count': 1}, {'name': 'correction', 'count': 1}]
    with repo.connect() as db:
        db.execute("UPDATE dream_queue SET error='private failure' WHERE memory_id=?", (hidden['id'],))
    scoped = repo.status(session_key='a', maintenance=False)
    assert scoped['counts']['knowledge'] == 2
    assert scoped['failed'] == 0 and scoped['last_dream'] is None

    matches = repo.search('New', session_key='a', expand_links=1)['memories']
    assert len(matches[0]['neighbors']) == 1
    assert matches[0]['neighbors'][0]['id'] == first['id']
    assert matches[0]['neighbors'][0]['status'] == 'superseded'
    exact = repo.search(newer['id'], session_key='a', expand_links=1)['memories'][0]
    assert exact['neighbors'][0]['id'] == first['id']


def test_catalog_and_search_roll_back_together(tmp_path, monkeypatch):
    repo = MemoryRepository(tmp_path)
    original = event(repo)
    monkeypatch.setattr(repo, '_chunk', lambda *_: (_ for _ in ()).throw(RuntimeError('Index interrupted')))
    with pytest.raises(RuntimeError):
        event(repo, 'Uncommitted correction', memory_id=original['id'], expected_revision=1)
    assert repo.read(original['id'], session_key='a')['revision'] == 1
    assert not repo.search('Uncommitted', session_key='a')['memories']


def test_local_date_boundaries_and_derived_event_time(tmp_path):
    repo = MemoryRepository(tmp_path)
    original = event(repo, observed_at='2024-02-29T00:15:00+08:00')
    learned = event(repo, 'Derived result', layer='knowledge', based_on=original['id'])
    assert learned['observed_at'] == original['observed_at']
    filters = dict(session_key='a', purpose='knowledge', since='2024-02-29', until='2024-02-29')
    assert not repo.search('Derived', **filters)['memories']
    assert repo.search('Derived', time_zone='Asia/Shanghai', **filters)['memories'][0]['id'] == learned['id']


def test_tampered_target_body_is_not_accepted_as_a_saved_result(tmp_path):
    repo = MemoryRepository(tmp_path)
    original = event(repo)
    token, _ = repo.pending()
    target = event(repo, 'Grounded result', layer='knowledge', based_on=original['id'], enqueue=False)
    repo.confirm(token, original['id'], 1, 'created', [target['id']], 'Result saved', session_key='a')
    (tmp_path / target['path']).write_text('Tampered body')
    assert repo.finish(token)['retained'] == 1
