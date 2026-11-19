"""Memory endpoint settings reject unusable addresses before publication."""

import pytest
from cirno_core.config.schema import Config
from cirno_server.webui.settings.contracts import WebUISettingsError
from cirno_server.webui.settings.runtime import update_runtime_config


@pytest.mark.parametrize("endpoint", [
    "https://embedding.test:65536/v1",
    "https://embedding.test:0/v1",
    "https://embedding.test:invalid/v1",
    "https://@embedding.test/v1",
    "https://embedding.test/v1?",
    "https://embedding.test/v1#",
])
def test_invalid_embedding_endpoint_does_not_replace_settings(endpoint):
    config = Config()
    before = config.model_dump(mode="json")
    with pytest.raises(WebUISettingsError, match="embedding"):
        update_runtime_config(config, {"agents.defaults.memory.embedding_api_base": endpoint})
    assert config.model_dump(mode="json") == before


@pytest.mark.parametrize("endpoint,expected", [
    ("https://embedding.test/v1/", "https://embedding.test/v1"),
    ("http://127.0.0.1:8765/v1", "http://127.0.0.1:8765/v1"),
    ("http://[::1]:8765/v1", "http://[::1]:8765/v1"),
    ("https://embedding.test/custom/embeddings", "https://embedding.test/custom/embeddings"),
])
def test_valid_embedding_endpoint_keeps_its_path_and_connection_settings(endpoint, expected):
    config = Config()
    config.agents.defaults.memory.embedding_api_key = "fixture"
    assert update_runtime_config(config, {"agents.defaults.memory.embedding_api_base": endpoint})
    assert config.agents.defaults.memory.embedding_api_base == expected
    assert config.agents.defaults.memory.embedding_api_key == "fixture"
