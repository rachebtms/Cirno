"""External marketplace response boundaries, using fake client objects only."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_server.webui import skills_marketplace as module


@pytest.mark.parametrize('provider', ['skills_sh', 'skillhub'])
@pytest.mark.parametrize('action', ['search', 'trending'])
@pytest.mark.parametrize('shape', ['null-root', 'list-root', 'null-rows', 'number-rows'])
async def test_invalid_catalog_shapes_report_a_safe_provider_failure(tmp_path, monkeypatch, provider, action, shape):
    key = 'results' if provider == 'skillhub' and action == 'search' else 'skills'
    payload = {'null-root': None, 'list-root': [], 'null-rows': {key: None}, 'number-rows': {key: 4}}[shape]
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    @asynccontextmanager
    async def client():
        yield SimpleNamespace(get=AsyncMock(return_value=response))

    monkeypatch.setattr(module, '_skills_client' if provider == 'skills_sh' else '_skillhub_client', client)
    if action == 'search':
        run = module.search_marketplace_skills('fixture', tmp_path, provider=provider, home_path=tmp_path / 'home')
    else:
        run = module.trending_marketplace_skills(tmp_path, provider=provider, home_path=tmp_path / 'home')
    with pytest.raises(module.SkillsMarketplaceError) as caught:
        await run
    assert caught.value.status == 502
    assert 'temporarily unavailable' in caught.value.message


@pytest.mark.parametrize('provider', ['skills_sh', 'skillhub'])
def test_boolean_install_counters_are_not_exposed_as_numeric_metrics(provider):
    if provider == 'skills_sh':
        result = module._marketplace_skill({'source': 'team/research', 'skillId': 'fixture', 'installs': True}, set())
    else:
        result = module._skillhub_skill({'slug': 'fixture', 'installs': True, 'downloads': True}, set())
    assert type(result['installs']) is int
    assert result['installs'] == 0
    if provider == 'skillhub':
        assert type(result['downloads']) is int
        assert result['downloads'] == 0


@pytest.mark.parametrize('broken', ['skills_sh', 'skillhub'])
@pytest.mark.parametrize('action', ['search', 'trending'])
async def test_bad_shapes_leave_the_other_catalog_visible_with_a_warning(tmp_path, monkeypatch, broken, action):
    for provider in ('skills_sh', 'skillhub'):
        if provider == broken:
            payload = None
        elif provider == 'skills_sh':
            payload = {'skills': [{'source': 'team/research', 'skillId': 'healthy-fixture'}]}
        else:
            payload = {'results' if action == 'search' else 'skills': [{'slug': 'healthy-fixture'}]}
        response = SimpleNamespace(raise_for_status=lambda: None, json=lambda payload=payload: payload)

        @asynccontextmanager
        async def client(response=response):
            yield SimpleNamespace(get=AsyncMock(return_value=response))

        monkeypatch.setattr(module, '_skills_client' if provider == 'skills_sh' else '_skillhub_client', client)
    result = (await module.search_marketplace_skills('fixture', tmp_path, home_path=tmp_path / 'home')
              if action == 'search' else await module.trending_marketplace_skills(tmp_path, home_path=tmp_path / 'home'))
    assert [item['skill_id'] for item in result['skills']] == ['healthy-fixture']
    assert result['warnings'][0]['provider'] == broken
    assert 'temporarily unavailable' in result['warnings'][0]['message']


@pytest.mark.parametrize('requested_version', ['', '1.0'])
async def test_bad_install_metadata_is_a_safe_upstream_error_not_an_internal_error(tmp_path, monkeypatch, requested_version):
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: None)

    @asynccontextmanager
    async def client():
        yield SimpleNamespace(get=AsyncMock(return_value=response))

    monkeypatch.setattr(module, '_skillhub_client', client)
    download = AsyncMock(side_effect=AssertionError('must not download invalid metadata'))
    monkeypatch.setattr(module, '_download_skillhub_archive', download)
    with pytest.raises(module.SkillsMarketplaceError) as caught:
        await module.install_marketplace_skill('', 'fixture', tmp_path / 'workspace', provider='skillhub',
            version=requested_version, home_path=tmp_path / 'home')
    assert caught.value.status == 502
    download.assert_not_awaited()


@pytest.mark.parametrize('bad_payload', [None, {'skills': None}])
async def test_an_invalid_weekly_page_does_not_hide_healthy_history_or_poison_the_cache(monkeypatch, bad_payload):
    good = {'skills': [{'source': 'team/research', 'skillId': 'fixture', 'weeklyInstalls': [1, 2]}]}
    def response(payload):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)
    client = SimpleNamespace(get=AsyncMock(side_effect=[response(bad_payload), response(good)]))
    monkeypatch.setattr(module, '_weekly_cache', {})
    monkeypatch.setattr(module, '_weekly_cache_expires_at', 0)
    result = await module._load_weekly_installs(client)
    assert result == {('team/research', 'fixture'): [1, 2]}
    assert module._weekly_cache == result
