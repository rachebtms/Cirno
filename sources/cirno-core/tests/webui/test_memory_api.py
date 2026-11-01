"""Authenticated settings actions expose bounded memory pages, evidence and maintenance."""
import pytest

from cirno.config.home import get_home_path
from cirno.config.schema import Config
from cirno.memory.repository import MemoryRepository
from cirno.webui.instance_api import instance_action
from cirno.webui.settings.runtime import update_runtime_config
from cirno.webui.settings.contracts import WebUISettingsError


@pytest.mark.asyncio
async def test_memory_settings_pagination_history_and_source():
    repo = MemoryRepository()
    row = repo.save("seed=42 threshold=0.00003125", source="test:original", session_key="a", kind="fact")
    repo.save("seed=43 threshold=0.00003125", source="test:correction", session_key="a", memory_id=row["id"], expected_revision=1)
    async def api(action, **values):
        return await instance_action({"action": action, "values": values}, sessions=None, bus=None)
    page = await api("memory.list", query="threshold", limit=1)
    assert len(page["memories"]) == 1
    assert page["memories"][0]["revision"] == 2
    assert (await api("memory.read", id=row["id"], revision=1))["content"].startswith("seed=42")
    assert len((await api("memory.history", id=row["id"]))["revisions"]) == 2
    assert (await api("memory.status"))["pending"] == 1
    token, _ = repo.pending()
    repo.finish(token, error="provider timeout")
    assert (await api("memory.status"))["last_dream"]["error"] == "provider timeout"
    assert (await api("memory.retry"))["retried"] == 1
    assert (await api("memory.reindex"))["scanned"] == 1
    assert get_home_path() in repo.path.parents


def test_memory_runtime_settings_round_trip_and_atomic_validation():
    config = Config()
    values = {"agents.defaults.dream.mode": "idle", "agents.defaults.dream.idle_after_seconds": 240,
              "agents.defaults.dream.batch_entries": 6, "agents.defaults.dream.batch_chars": 8000,
              "agents.defaults.memory.context_tokens": 1024, "agents.defaults.memory.checkpoint_tokens": 2048,
              "agents.defaults.memory.index_scan_batch": 80, "agents.defaults.memory.embedding_enabled": False}
    assert update_runtime_config(config, values, local_browser=True)
    assert config.agents.defaults.memory.context_tokens == 1024
    assert config.agents.defaults.dream.batch_entries == 6
    previous = config.model_dump()
    with pytest.raises(WebUISettingsError):
        update_runtime_config(config, {"agents.defaults.memory.embedding_max_rss_mb": 0,
                                       "agents.defaults.dream.batch_entries": 4}, local_browser=True)
    assert config.model_dump() == previous


@pytest.mark.asyncio
async def test_settings_tags_dates_and_database_status():
    repo = MemoryRepository()
    row = repo.save('Historical calibration', source='test:dated', session_key='a', tags=['calibration'], observed_at='2024-02-29T12:00:00Z')
    async def api(action, **values):
        return await instance_action({'action': action, 'values': values}, sessions=None, bus=None)
    result = await api('memory.list', since='2024-02-29', until='2024-02-29', time_field='observed_at')
    assert [r['id'] for r in result['memories']] == [row['id']]
    assert (await api('memory.tags'))['tags'] == [{'name': 'calibration', 'count': 1}]
    assert set((await api('memory.status'))['databases']) == {'catalog.sqlite3', 'search.sqlite3', 'dream.sqlite3'}


@pytest.mark.asyncio
async def test_settings_uses_shared_semantic_search_and_preserves_filters(monkeypatch):
    import cirno.memory.embedding as embedding
    seen = {}
    def semantic(repo, query, config, **filters):
        seen.update(query=query, enabled=config.embedding_enabled, **filters)
        return {"memories": [], "engine": "hybrid", "has_more": False, "next_offset": 0, "embedding_index_pending": True}
    monkeypatch.setattr(embedding, 'search', semantic)
    result = await instance_action({'action': 'memory.list', 'values': {
        'query': 'calibration', 'mode': 'hybrid', 'scope': 'project', 'layer': 'knowledge',
        'tags': ['calibration'], 'since': '2024-02-29', 'time_zone': 'Asia/Shanghai', 'limit': 10,
    }}, sessions=None, bus=None)
    assert result['engine'] == result['requested_mode'] == 'hybrid'
    assert result['embedding_index_pending'] is True
    assert result['time_zone'] == 'Asia/Shanghai'
    assert seen['maintenance'] is True
    assert seen['scope'] == 'project' and seen['tags'] == ['calibration']
    assert seen['since'] == '2024-02-29' and seen['limit'] == 10


@pytest.mark.asyncio
async def test_settings_disabled_embedding_falls_back_with_reason():
    repo = MemoryRepository()
    row = repo.save('calibration', source='test:fallback', session_key='a', layer='knowledge')
    result = await instance_action({'action': 'memory.list', 'values': {
        'query': 'calibration', 'mode': 'semantic',
    }}, sessions=None, bus=None)
    assert result['engine'] == 'bm25' and result['requested_mode'] == 'semantic'
    assert result['warning_code'] == 'disabled'
    assert result['memories'][0]['id'] == row['id']
    assert not (repo.root / 'vectors.sqlite3').exists()
