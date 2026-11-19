"""Optional vector-cache failures preserve authoritative lexical retrieval."""

import sqlite3
from contextlib import contextmanager

import pytest
from cirno_memory.config import MemoryConfig
from cirno_memory.embedding import search
from cirno_memory.repository import MemoryRepository


@pytest.mark.parametrize("failure", ["corrupt", "read-only"])
def test_vector_cache_database_failures_fall_back_without_launching_inference(tmp_path, monkeypatch, failure):
    repo = MemoryRepository(tmp_path)
    record = repo.save("marker durable finding", source="test:fixture", session_key="fixture", layer="knowledge")
    model, tokenizer = tmp_path / "model.onnx", tmp_path / "tokenizer.json"
    model.write_bytes(b"fixture")
    tokenizer.write_bytes(b"fixture")
    config = MemoryConfig(embedding_enabled=True, embedding_model_path=str(model), embedding_tokenizer_path=str(tokenizer))
    if failure == "corrupt":
        (repo.root / "vectors.sqlite3").write_bytes(b"corrupt optional vector cache")
    else:
        connect = repo.connect

        @contextmanager
        def read_only_vectors(*, vectors=False):
            with connect(vectors=vectors) as db:
                if vectors:
                    db.execute("PRAGMA query_only=ON")
                yield db

        monkeypatch.setattr(repo, "connect", read_only_vectors)
    monkeypatch.setattr("cirno_memory.embedding.EmbeddingWorker", lambda *_args: pytest.fail("Broken cache must not launch inference"))
    result = search(repo, "marker", config, session_key="fixture")
    assert result["engine"] == "bm25"
    assert result["warning_code"] == "unavailable"
    assert result["warning"]
    assert result["memories"][0]["id"] == record["id"]
    assert repo.read(record["id"], session_key="fixture")["content"] == "marker durable finding"


@pytest.mark.parametrize("database", ["catalog", "search"])
def test_authoritative_lexical_database_failures_are_not_reported_as_optional_fallback(tmp_path, monkeypatch, database):
    repo = MemoryRepository(tmp_path)
    repo.save("marker durable finding", source="test:fixture", session_key="fixture", layer="knowledge")
    (repo.root / f"{database}.sqlite3").write_bytes(b"broken authoritative database")
    monkeypatch.setattr("cirno_memory.embedding.EmbeddingWorker", lambda *_args: pytest.fail("Unavailable source must not launch inference"))
    with pytest.raises(sqlite3.DatabaseError):
        search(repo, "marker", MemoryConfig(embedding_enabled=True), session_key="fixture")
