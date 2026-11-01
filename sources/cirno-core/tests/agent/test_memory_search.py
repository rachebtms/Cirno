"""Both retrieval callers share the same routing and low-resource fallbacks."""
import pytest

from cirno.config.schema import MemoryConfig
from cirno.memory.repository import MemoryRepository
from cirno.memory.search import search


def test_browsing_and_evidence_do_not_start_inference(tmp_path, monkeypatch):
    import cirno.memory.embedding as embedding
    def forbidden(*args, **kwargs):
        pytest.fail('Metadata/evidence must not start semantic retrieval')
    monkeypatch.setattr(embedding, 'search', forbidden)
    repo = MemoryRepository(tmp_path)
    row = repo.save('calibration', source='test:raw', session_key='a')
    config = MemoryConfig(embedding_enabled=True)
    assert search(repo, '', config, mode='hybrid', session_key='a')['memories'][0]['id'] == row['id']
    for filters in ({'layer': 'event'}, {'include_history': True}, {'purpose': 'evidence'}, {'layer': 'task'}):
        result = search(repo, 'calibration', config, mode='semantic', session_key='a', **filters)
        assert result['engine'] == 'bm25' and result['warning_code'] == 'lexical_only'
    assert not (repo.root / 'vectors.sqlite3').exists()


def test_reject_unknown_mode(tmp_path):
    with pytest.raises(ValueError, match='mode'):
        search(MemoryRepository(tmp_path), 'query', MemoryConfig(), mode='typo')
