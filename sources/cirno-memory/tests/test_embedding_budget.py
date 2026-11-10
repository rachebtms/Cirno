"""Cold startup, pipe backpressure and successive API batches share one deadline."""
import os
import subprocess
import sys
import time

import httpx
import pytest
from cirno_memory.config import MemoryConfig
from cirno_memory.embedding import EmbeddingWorker
from cirno_memory.embedding_api import APIEmbeddingWorker


def worker(program, *, budget=512):
    instance = EmbeddingWorker(MemoryConfig(embedding_max_rss_mb=budget))
    instance.process = subprocess.Popen([sys.executable, "-c", program], stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
    return instance


@pytest.mark.skipif(os.name != "posix", reason="Local pipe selector backend requires POSIX")
@pytest.mark.parametrize("budget", [200, 512])
def test_reported_207_mib_peak_obeys_configured_budget(budget):
    instance = worker('import sys\nsys.stdin.readline()\nprint(\'{"peak_mb":207.8,"vectors":[[1,0]]}\', flush=True)', budget=budget)
    try:
        if budget == 200:
            with pytest.raises(MemoryError, match="207.8 MB exceeds configured limit of 200 MB"):
                instance.request(["query"])
        else:
            assert instance.request(["query"])["vectors"] == [[1, 0]]
    finally:
        instance.__exit__()


@pytest.mark.skipif(os.name != "posix", reason="Local pipe selector backend requires POSIX")
@pytest.mark.parametrize("program", [
    'import time\ntime.sleep(10)',
    'import sys,time\nsys.stdin.readline()\nsys.stdout.write(\'{"vectors":\')\nsys.stdout.flush()\ntime.sleep(10)',
])
def test_blocked_input_and_partial_response_cannot_bypass_timeout(program):
    instance = worker(program)
    instance.budget.deadline = time.monotonic() + 0.15
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="time budget"):
            instance.request(["文" * 64000])
        assert time.monotonic() - started < 2
    finally:
        instance.__exit__()
    assert instance.process.poll() is not None


def test_api_batches_share_one_budget_and_expired_work_is_not_sent(monkeypatch):
    import cirno_memory.embedding_budget as budget
    import cirno_memory.embedding_api as api
    clock = [0.0]
    monkeypatch.setattr(budget.time, "monotonic", lambda: clock[0])
    original = httpx.Client
    calls = []
    def respond(request):
        calls.append(request)
        clock[0] += 0.6
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1., 0.]}]})
    monkeypatch.setattr(api.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs))
    config = MemoryConfig(embedding_provider="api", embedding_api_base="https://embedding.invalid/v1", embedding_api_model="test", embedding_timeout_seconds=1)
    with APIEmbeddingWorker(config) as instance:
        assert instance.request(["query"])["vectors"] == [[1., 0.]]
        with pytest.raises(TimeoutError, match="time budget"):
            instance.request(["next chunk"])
        with pytest.raises(TimeoutError, match="time budget"):
            instance.request(["already expired"])
    assert len(calls) == 2
    assert calls[1].extensions["timeout"]["read"] == pytest.approx(0.4)


def test_cached_vector_scoring_obeys_the_whole_search_deadline(tmp_path, monkeypatch):
    import cirno_memory.embedding as embedding
    import cirno_memory.embedding_budget as budget
    from cirno_memory.repository import MemoryRepository

    class Worker:
        peak_mb = 1
        def __init__(self, config):
            self.budget = budget.EmbeddingBudget(config.embedding_timeout_seconds)
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def request(self, texts, **options):
            if not options:
                return {"vectors": [[1.0]]}
            return {"vectors": [[1.0], [1.0]], "chunks": [
                {"chunk_index": index, "start_char": 0, "end_char": 5} for index in range(2)
            ], "has_more": False}

    clock = [0.0]
    monkeypatch.setattr(budget.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(embedding, "EmbeddingWorker", Worker)
    monkeypatch.setattr(embedding, "_fingerprint", lambda _: "test")
    repo = MemoryRepository(tmp_path)
    repo.save("marker evidence", source="test:result", session_key="a", layer="knowledge")
    config = MemoryConfig(embedding_enabled=True, embedding_timeout_seconds=1)
    assert embedding.search(repo, "marker", config, session_key="a")["engine"] == "hybrid"
    unpack = embedding.struct.unpack
    scored = []
    def slow_score(*args):
        scored.append(1)
        clock[0] += 2
        return unpack(*args)
    monkeypatch.setattr(embedding.struct, "unpack", slow_score)
    result = embedding.search(repo, "marker", config, session_key="a")
    assert result["engine"] == "bm25"
    assert result["warning_code"] == "unavailable"
    assert "time budget" in result["warning"]
    assert len(scored) == 1
