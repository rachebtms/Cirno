"""Local embedding setup and monitoring share the search's remaining budget."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cirno_memory.config import MemoryConfig
from cirno_memory.embedding import EmbeddingWorker, search
from cirno_memory.repository import MemoryRepository


@pytest.mark.parametrize("monitor_seconds", [0.08, 0.12], ids=["partial-budget", "expired-budget"])
def test_process_monitoring_cannot_spend_or_wait_past_the_remaining_budget(monkeypatch, monitor_seconds):
    clock = [0.0]
    monkeypatch.setattr("cirno_memory.embedding_budget.time.monotonic", lambda: clock[0])
    worker = EmbeddingWorker(MemoryConfig())
    worker.budget.deadline = 0.1
    worker.process = SimpleNamespace(pid=123, stdin=SimpleNamespace(fileno=lambda: 1001), stdout=SimpleNamespace(fileno=lambda: 1002))
    monitors, waits = [], []

    def monitor(*_args, **kwargs):
        monitors.append(kwargs["timeout"])
        clock[0] += monitor_seconds
        return SimpleNamespace(stdout="0")

    class Selector:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def register(self, *_args):
            pass

        def unregister(self, *_args):
            pass

        def select(self, *, timeout):
            waits.append(timeout)
            return [(SimpleNamespace(fileobj=worker.process.stdin), 2), (SimpleNamespace(fileobj=worker.process.stdout), 1)]

    monkeypatch.setattr("cirno_memory.embedding.subprocess.run", monitor)
    monkeypatch.setattr("cirno_memory.embedding.selectors.DefaultSelector", Selector)
    monkeypatch.setattr("cirno_memory.embedding.os.set_blocking", lambda *_args: None)
    monkeypatch.setattr("cirno_memory.embedding.os.write", lambda _fd, data: len(data))
    monkeypatch.setattr("cirno_memory.embedding.os.read", lambda *_args: json.dumps({"vectors": [[1, 0]], "peak_mb": 0}).encode() + b"\n")
    if monitor_seconds > 0.1:
        with pytest.raises(TimeoutError):
            worker.request(["fixture"])
        assert waits == []
    else:
        assert worker.request(["fixture"])["vectors"] == [[1, 0]]
        assert waits == [pytest.approx(0.02)]
    assert monitors == [pytest.approx(0.1)]


def test_search_stops_hashing_model_files_when_its_whole_budget_expires(tmp_path, monkeypatch):
    clock, reads = [0.0], []
    repo = MemoryRepository(tmp_path / "home")
    repo.save("fixture finding", source="test:fixture", session_key="fixture", layer="knowledge")
    model, tokenizer = tmp_path / "model.onnx", tmp_path / "tokenizer.json"
    config = MemoryConfig(embedding_enabled=True, embedding_model_path=str(model), embedding_tokenizer_path=str(tokenizer), embedding_timeout_seconds=1)
    original = Path.open

    class Stream:
        def __init__(self):
            self.chunks = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self, _size):
            reads.append(1)
            clock[0] += 0.6
            self.chunks += 1
            return b"fixture model bytes" if self.chunks <= 3 else b""

    def open_file(path, *_args, **kwargs):
        return Stream() if path in {model, tokenizer} else original(path, *_args, **kwargs)

    monkeypatch.setattr("cirno_memory.embedding_budget.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(Path, "open", open_file)
    monkeypatch.setattr("cirno_memory.embedding.EmbeddingWorker", lambda *_args: pytest.fail("Expired setup must not launch inference"))
    result = search(repo, "fixture", config, session_key="fixture")
    assert result["engine"] == "bm25"
    assert "time budget" in result["warning"]
    assert len(reads) == 2
    assert clock[0] == pytest.approx(1.2)
