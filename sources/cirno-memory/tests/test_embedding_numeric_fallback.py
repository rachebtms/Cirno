"""Malformed numeric API vectors cannot escape the visible lexical fallback."""

import json
from contextlib import contextmanager

import pytest
from cirno_memory.config import MemoryConfig
from cirno_memory.embedding import search
from cirno_memory.repository import MemoryRepository


def fake_api(monkeypatch, vector):
    class Response:
        status_code = 200

        def iter_bytes(self):
            yield json.dumps({"data": [{"index": 0, "embedding": vector}]}).encode()

    class Client:
        def __init__(self, **_kwargs):
            pass

        @contextmanager
        def stream(self, *_args, **_kwargs):
            yield Response()

        def close(self):
            pass

    monkeypatch.setattr("cirno_memory.embedding_api.httpx.Client", Client)


def retrieve(tmp_path):
    repo = MemoryRepository(tmp_path)
    row = repo.save("marker finding", source="test:fixture", session_key="fixture", layer="knowledge")
    config = MemoryConfig(embedding_enabled=True, embedding_provider="api",
                          embedding_api_base="https://embedding.invalid/v1", embedding_api_model="fixture")
    return row, search(repo, "marker", config, mode="semantic", session_key="fixture")


@pytest.mark.parametrize("value", [10**400, True, float("inf"), 0], ids=["unrepresentable", "boolean", "infinite", "zero"])
def test_unusable_api_numeric_vectors_return_a_visible_fallback(tmp_path, monkeypatch, value):
    fake_api(monkeypatch, [value, 0])
    row, result = retrieve(tmp_path)
    assert result["engine"] == "bm25"
    assert result["warning_code"] == "unavailable"
    assert result["memories"][0]["id"] == row["id"]
    assert "numeric" in result["warning"] or "norm" in result["warning"]


@pytest.mark.parametrize("vector", [[10**200, 0], [1e308, 1e308], [1e-300, 0], [3, 4]],
                         ids=["large-integer", "large-floats", "small-floats", "ordinary"])
def test_finite_nonzero_vectors_normalize_without_overflow_or_underflow(tmp_path, monkeypatch, vector):
    fake_api(monkeypatch, vector)
    row, result = retrieve(tmp_path)
    assert result["engine"] == "semantic"
    assert "warning_code" not in result
    assert result["memories"][0]["id"] == row["id"]
    assert result["memories"][0]["score"] == pytest.approx(1.0)
