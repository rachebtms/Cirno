"""External embeddings use the same bounded, resumable index as local inference."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from cirno_memory.config import MemoryConfig
from cirno_memory.embedding import search
from cirno_memory.repository import MemoryRepository


def test_real_http_api_indexes_long_tail_and_reuses_disk_chunks(tmp_path):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((self.path, self.headers.get('Authorization'), body))
            vectors = [{'index': index, 'embedding': [0., 4.] if 'uniquetail' in text else [3., 0.]}
                       for index, text in enumerate(body['input'])]
            data = json.dumps({'data': list(reversed(vectors))}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = MemoryConfig(embedding_enabled=True, embedding_provider='api', embedding_api_base=f'http://127.0.0.1:{server.server_port}/v1', embedding_api_key='fixture-key', embedding_api_model='small-model', embedding_api_chunk_chars=128)
        repo = MemoryRepository(tmp_path)
        record = repo.save('prefix ' * 700 + 'uniquetail', source='test:long', session_key='a', layer='knowledge')
        first = search(repo, 'uniquetail', config, mode='semantic', session_key='a')
        assert first['embedding_index_pending'] is True
        final = search(repo, 'uniquetail', config, mode='hybrid', session_key='a')
        assert final['embedding_index_pending'] is False
        assert final['memories'][0]['id'] == record['id']
        assert 'uniquetail' in final['memories'][0]['snippet']
        count = len(calls)
        search(repo, 'uniquetail', config, session_key='a')
        assert len(calls) == count + 1  # Only query embedding, not re-indexing.
        assert all(path == '/v1/embeddings' and auth == 'Bearer fixture-key' and body['model'] == 'small-model' and len(body['input']) <= 8 for path, auth, body in calls)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize('response', [
    httpx.Response(401, text='do not reveal provider credentials'),
    httpx.Response(200, json={'data': []}),
    httpx.Response(200, json={'data': [{'index': 0, 'embedding': [0., 0.]}]}),
    httpx.Response(200, json={'data': [{'index': 9, 'embedding': [1., 0.]}]}),
])
def test_invalid_api_result_visibly_falls_back_to_bm25(tmp_path, monkeypatch, response):
    import cirno_memory.embedding_api as module
    real_client = httpx.Client
    monkeypatch.setattr(module.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: response), **kwargs))
    repo = MemoryRepository(tmp_path)
    repo.save('calibration threshold', source='test:result', session_key='a', layer='knowledge')
    config = MemoryConfig(embedding_enabled=True, embedding_provider='api', embedding_api_base='https://embedding.invalid/v1', embedding_api_model='model')
    result = search(repo, 'calibration', config, session_key='a')
    assert result['engine'] == 'bm25' and result['warning_code'] == 'unavailable'
    assert result['memories'] and result['warning']
    assert 'do not reveal' not in result['warning']


def test_api_timeout_is_visible_without_loading_local_weights(tmp_path, monkeypatch):
    import cirno_memory.embedding_api as module
    real_client = httpx.Client
    def timeout(request):
        raise httpx.ReadTimeout('timeout', request=request)
    monkeypatch.setattr(module.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(timeout), **kwargs))
    repo = MemoryRepository(tmp_path)
    result = search(repo, 'query', MemoryConfig(embedding_enabled=True, embedding_provider='api', embedding_api_base='https://embedding.invalid/v1', embedding_api_model='model'))
    assert result['engine'] == 'bm25' and 'ReadTimeout' in result['warning']


def test_embedding_api_url_rejects_embedded_credentials():
    with pytest.raises(ValueError, match='without credentials'):
        MemoryConfig(embedding_api_base='https://owner:secret@embedding.invalid/v1')
