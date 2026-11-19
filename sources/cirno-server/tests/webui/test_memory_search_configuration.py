"""Memory search retains its configuration source and resolves runtime references."""

import json

import pytest
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.instance_features import MemoryTool
from cirno_core.config.home import set_instance_path
from cirno_core.config.loader import save_config, set_config_path
from cirno_core.config.schema import Config
from cirno_server.webui.instance_api import instance_action


def configured(path, *, model="fixture", base="https://embedding.invalid/v1"):
    config = Config()
    memory = config.agents.defaults.memory
    memory.embedding_enabled = True
    memory.embedding_provider = "api"
    memory.embedding_api_base = base
    memory.embedding_api_key = "${CIRNO_TEST_EMBEDDING_KEY}"
    memory.embedding_api_model = model
    save_config(config, path)
    return config


@pytest.mark.parametrize("entry", ["tool", "memory.list", "memory.graph"])
async def test_search_resolves_embedding_references_before_invoking_retrieval(tmp_path, monkeypatch, entry):
    root = tmp_path / "instance"
    path = root / "config.json"
    set_instance_path(root)
    set_config_path(path)
    monkeypatch.setenv("CIRNO_TEST_EMBEDDING_KEY", "fixture-resolved-key")
    monkeypatch.setenv("CIRNO_TEST_EMBEDDING_MODEL", "fixture-resolved-model")
    monkeypatch.setenv("CIRNO_TEST_EMBEDDING_BASE", "https://embedding.invalid/v1")
    configured(path, model="${CIRNO_TEST_EMBEDDING_MODEL}", base="${CIRNO_TEST_EMBEDDING_BASE}")
    observed = []

    def retrieve(_repo, _query, memory, **_filters):
        observed.append((memory.embedding_api_key, memory.embedding_api_model, memory.embedding_api_base))
        return {"memories": [], "engine": "hybrid", "has_more": False, "next_offset": 0}

    monkeypatch.setattr("cirno_memory.embedding.search", retrieve)
    if entry == "tool":
        with request_context(RequestContext("websocket", "fixture", session_key="websocket:fixture")):
            result = json.loads(await MemoryTool().execute("search", query="fixture", mode="hybrid"))
    else:
        result = await instance_action({"action": entry, "values": {"query": "fixture", "mode": "hybrid"}},
                                       sessions=None, bus=None, config_path=path)
    assert result["engine"] == "hybrid"
    assert observed == [("fixture-resolved-key", "fixture-resolved-model", "https://embedding.invalid/v1")]
    # Runtime substitution must not replace environment references on disk.
    assert "${CIRNO_TEST_EMBEDDING_KEY}" in path.read_text()
    assert "${CIRNO_TEST_EMBEDDING_BASE}" in path.read_text()


@pytest.mark.parametrize("action", ["memory.list", "memory.graph"])
async def test_memory_page_reads_the_server_config_path_instead_of_global_selection(tmp_path, monkeypatch, action):
    root = tmp_path / "instance"
    set_instance_path(root)
    path = root / "server.json"
    other = root / "unrelated.json"
    set_config_path(other)
    monkeypatch.setenv("CIRNO_TEST_EMBEDDING_KEY", "fixture-resolved-key")
    configured(path, model="server-model")
    configured(other, model="unrelated-model")
    observed = []

    def retrieve(_repo, _query, memory, **_filters):
        observed.append(memory.embedding_api_model)
        return {"memories": [], "engine": "hybrid", "has_more": False, "next_offset": 0}

    monkeypatch.setattr("cirno_memory.embedding.search", retrieve)
    await instance_action({"action": action, "values": {"query": "fixture", "mode": "hybrid"}},
                          sessions=None, bus=None, config_path=path)
    assert observed == ["server-model"]
