"""Bundled assets are defaults for blank paths, never overrides or opt-ins."""

import pytest
from cirno_memory.config import MemoryConfig


@pytest.mark.parametrize("data", [{}, {"embeddingModelPath": "", "embeddingTokenizerPath": ""}])
def test_bundled_assets_fill_missing_and_persisted_blank_paths(monkeypatch, tmp_path, data):
    monkeypatch.setenv("CIRNO_BUNDLED_EMBEDDING_DIR", str(tmp_path))
    config = MemoryConfig.model_validate(data)
    assert config.embedding_model_path == str(tmp_path / "model_quantized.onnx")
    assert config.embedding_tokenizer_path == str(tmp_path / "tokenizer.json")
    assert not config.embedding_enabled


def test_custom_paths_override_bundled_assets(monkeypatch):
    monkeypatch.setenv("CIRNO_BUNDLED_EMBEDDING_DIR", "/bundled")
    config = MemoryConfig(
        embedding_model_path="/custom/model.onnx", embedding_tokenizer_path="/custom/tokens.json"
    )
    assert config.embedding_model_path == "/custom/model.onnx"
    assert config.embedding_tokenizer_path == "/custom/tokens.json"


def test_no_bundled_assets_preserves_empty_paths(monkeypatch):
    monkeypatch.delenv("CIRNO_BUNDLED_EMBEDDING_DIR", raising=False)
    config = MemoryConfig()
    assert config.embedding_model_path == config.embedding_tokenizer_path == ""
