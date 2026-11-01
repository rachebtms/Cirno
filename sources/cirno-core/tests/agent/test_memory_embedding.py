import sys

from cirno.config.schema import MemoryConfig
from cirno.memory.embedding import search
from cirno.memory.repository import MemoryRepository


def test_default_bm25_never_imports_inference_runtime(tmp_path):
    repo = MemoryRepository(tmp_path)
    record = repo.save("entropy=0.001", source="test:result", session_key="a", layer="knowledge")
    before = set(sys.modules)
    result = search(repo, "entropy", MemoryConfig(), session_key="a")
    assert result["memories"][0]["id"] == record["id"]
    assert result["engine"] == "bm25"
    assert not ({"numpy", "onnxruntime", "tokenizers"} & (set(sys.modules) - before))


def test_bad_optional_model_is_a_visible_bm25_fallback(tmp_path):
    repo = MemoryRepository(tmp_path)
    repo.save("exact threshold=0.001", source="test:result", session_key="a")
    result = search(repo, "threshold", MemoryConfig(embedding_enabled=True, embedding_model_path="missing"), session_key="a")
    assert result["memories"]
    assert result["warning"]
    assert result["engine"] == "bm25"


def test_chunk_index_resumes_and_matches_a_long_records_tail(tmp_path, monkeypatch):
    import cirno.memory.embedding as embedding

    class Worker:
        peak_mb = 120

        def __init__(self, _config):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def request(self, texts, **options):
            if not options.get('chunked'):
                return {'vectors': [[1., 0.]]}
            text = texts[0]
            starts = range(0, len(text), 192)
            first = options['start_chunk']
            chosen = list(starts[first:first + options['max_chunks']])
            chunks = [{'chunk_index': first+i, 'start_char': start, 'end_char': min(start+224, len(text))} for i, start in enumerate(chosen)]
            return {'vectors': [[1., 0.] if 'uniquetail' in text[c['start_char']:c['end_char']] else [0., 1.] for c in chunks],
                    'chunks': chunks, 'has_more': first+len(chunks)<len(starts)}

    monkeypatch.setattr(embedding, 'EmbeddingWorker', Worker)
    model, tokenizer = tmp_path / 'model', tmp_path / 'tokenizer'
    model.write_text('model'); tokenizer.write_text('tokenizer')
    config = MemoryConfig(embedding_enabled=True, embedding_model_path=str(model), embedding_tokenizer_path=str(tokenizer))
    repo = MemoryRepository(tmp_path)
    record = repo.save('prefix ' * 950 + ' uniquetail', source='test:long', session_key='a', layer='knowledge')
    first = search(repo, 'uniquetail', config, mode='semantic', session_key='a')
    assert first['embedding_index_pending'] is True
    with repo.connect(vectors=True) as db:
        assert db.execute('SELECT count(*) FROM vector_chunks').fetchone()[0] == 32
    final = search(repo, 'uniquetail', config, mode='semantic', session_key='a')
    assert final['embedding_index_pending'] is False
    assert final['memories'][0]['id'] == record['id']
    assert final['memories'][0]['score'] == 1
    assert 'uniquetail' in final['memories'][0]['snippet']
    assert final['memories'][0]['start_char'] > 4000
    assert (repo.root / 'vectors.sqlite3').exists()
