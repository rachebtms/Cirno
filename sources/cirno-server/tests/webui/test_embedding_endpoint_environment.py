"""Resolve embedding endpoint references without publishing secrets or bad URLs."""

import json
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from cirno_core.config.errors import ConfigLoadError
from cirno_core.config.loader import load_config, resolve_config_env_vars
from cirno_memory.config import MemoryConfig
from cirno_memory.embedding import _fingerprint
from cirno_memory.embedding_api import APIEmbeddingWorker
from cirno_memory.repository import MemoryRepository
from cirno_memory.search import search


@pytest.mark.parametrize("template", ["${CIRNO_TEST_EMBED_BASE}", "https://${CIRNO_TEST_EMBED_HOST}/v1/"])
def test_endpoint_references_resolve_before_a_fake_request_and_stay_on_disk(tmp_path, monkeypatch, template):
    monkeypatch.setenv("CIRNO_TEST_EMBED_BASE", "https://embedding.test/v1/")
    monkeypatch.setenv("CIRNO_TEST_EMBED_HOST", "embedding.test")
    path = tmp_path / "config.json"
    raw = json.dumps({"agents": {"defaults": {"memory": {
        "embeddingProvider": "api", "embeddingApiBase": template, "embeddingApiModel": "fixture",
    }}}})
    path.write_text(raw)
    calls = []
    class Client:
        def __init__(self, **_kwargs):
            pass

        @contextmanager
        def stream(self, _method, endpoint, **_kwargs):
            calls.append(endpoint)
            class Response:
                status_code = 200

                def iter_bytes(self):
                    yield b'{"data":[{"index":0,"embedding":[3,4]}]}'
            yield Response()

        def close(self):
            pass
    monkeypatch.setattr("cirno_memory.embedding_api.httpx.Client", Client)
    loaded = load_config(path)
    assert loaded.agents.defaults.memory.embedding_api_base == template
    resolved = resolve_config_env_vars(loaded, config_path=path)
    with APIEmbeddingWorker(resolved.agents.defaults.memory) as worker:
        assert worker.request(["query"])["vectors"][0] == pytest.approx([0.6, 0.8])
    assert calls == ["https://embedding.test/v1/embeddings"]
    assert path.read_text() == raw
    assert loaded.agents.defaults.memory.embedding_api_base == template


def test_missing_endpoint_environment_reference_reports_its_selected_config(tmp_path, monkeypatch):
    monkeypatch.delenv("CIRNO_TEST_EMBED_BASE", raising=False)
    path = tmp_path / "selected.json"
    path.write_text(json.dumps({"agents": {"defaults": {"memory": {"embeddingApiBase": "${CIRNO_TEST_EMBED_BASE}"}}}}))
    loaded = load_config(path)
    with pytest.raises(ConfigLoadError) as error:
        resolve_config_env_vars(loaded, config_path=path)
    assert error.value.path == path
    assert error.value.kind == "missing_env"


@pytest.mark.parametrize("endpoint", [
    "https://embedding.test:65536/v1",
    "https://owner:fixture-secret@embedding.test/v1",
    "https://embedding.test/v1?",
    "${CIRNO_TEST_EMBED_BASE}",
])
def test_runtime_endpoint_validation_precedes_http_client_creation(monkeypatch, endpoint):
    config = MemoryConfig(embedding_provider="api", embedding_api_base="https://embedding.test/v1", embedding_api_model="fixture")
    # The generic runtime resolver uses model_copy updates after loading raw refs.
    resolved = config.model_copy(update={"embedding_api_base": endpoint})
    client = Mock()
    monkeypatch.setattr("cirno_memory.embedding_api.httpx.Client", client)
    with pytest.raises(ValueError) as error, APIEmbeddingWorker(resolved):
        pass
    client.assert_not_called()
    assert "fixture-secret" not in str(error.value)


@pytest.mark.parametrize("endpoint", ["https://owner:fixture-secret@embedding.test/v1", "${CIRNO_TEST_EMBED_BASE}"])
def test_bad_runtime_endpoint_returns_visible_lexical_fallback_without_http(tmp_path, monkeypatch, endpoint):
    repo = MemoryRepository(tmp_path)
    row = repo.save("calibration marker", source="test:fixture", session_key="fixture", layer="knowledge")
    config = MemoryConfig(embedding_enabled=True, embedding_provider="api", embedding_api_base="https://embedding.test/v1", embedding_api_model="fixture")
    resolved = config.model_copy(update={"embedding_api_base": endpoint})
    client = Mock(side_effect=AssertionError("invalid endpoint reached HTTP client"))
    monkeypatch.setattr("cirno_memory.embedding_api.httpx.Client", client)
    result = search(repo, "calibration", resolved, mode="semantic", session_key="fixture")
    assert result["engine"] == "bm25"
    assert result["warning_code"] == "unavailable"
    assert result["memories"][0]["id"] == row["id"]
    assert "fixture-secret" not in result["warning"]
    client.assert_not_called()


def test_valid_existing_endpoint_fingerprint_stays_compatible():
    config = MemoryConfig(embedding_provider="api", embedding_api_base="https://embedding.test/v1", embedding_api_model="fixture")
    assert _fingerprint(config) == "9f46bbe11680614ca7462e9cb1103a0e44b5b4f8ada2da8e1bd6a31b9b09b96b"
