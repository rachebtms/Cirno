"""Gateway Skill ownership with tiny packages and client/process factories forbidden."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.agent import plugins
from cirno_core.config.home import set_instance_path
from cirno_server.webui import skills_marketplace as market
from cirno_server.webui.http.skills import SkillsRoutes
from cirno_server.webui.settings.services import WebUISettingsServices
from websockets.datastructures import Headers


@pytest.fixture
def owned(tmp_path, monkeypatch):
    workspace = tmp_path / 'workspace'
    package = workspace / 'plugins' / 'owner-plugin'
    package.mkdir(parents=True)
    (package / 'plugin.json').write_text(json.dumps({'$schema': plugins.AGENT_PLUGIN_SCHEMA, 'name': 'owner-plugin'}))
    skill = package / 'skills' / 'owner-skill'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: owner-skill\ndescription: Owned plugin\n---\nOwned instructions\n')
    first, second = tmp_path / 'first' / 'config.json', tmp_path / 'second' / 'config.json'
    home = tmp_path / 'owned-instance' / 'home'
    set_instance_path(home.parent)
    monkeypatch.setattr('cirno_core.config.loader._current_config_path', first)
    plugins.set_agent_plugin_enabled(workspace, 'owner-plugin', True, config_path=first)
    server = SimpleNamespace(settings=WebUISettingsServices.create(first, home_path=home),
        skills_workspace_path=workspace, disabled_skills=set(), check_api_token=lambda request: True,
        _skill_install_lock=asyncio.Lock(), skill_state_action=None, _log=SimpleNamespace(exception=Mock()))
    server.skills_routes = SkillsRoutes(server)
    return server, first, second


def request(**payload):
    return SimpleNamespace(path='/v0/skills', headers=Headers(), _cirno_webui_mutation_request=True,
        _cirno_webui_mutation_payload=payload)


@pytest.mark.parametrize('action', ['catalog', 'detail', 'disable'])
async def test_gateway_skill_routes_use_their_captured_plugin_configuration(owned, monkeypatch, action):
    server, first, second = owned
    monkeypatch.setattr('cirno_core.config.loader._current_config_path', second)
    if action == 'catalog':
        result = await server.skills_routes._load_webui_skills()
        assert any(item['name'] == 'owner-skill' for item in result['skills'])
    elif action == 'detail':
        result = await server.skills_routes._handle_webui_skill_detail(request(), 'owner-skill')
        assert result.status_code == 200
        assert 'Owned instructions' in json.loads(result.body)['raw_markdown']
    else:
        result = await server.skills_routes._handle_webui_skill_update(request(name='owner-skill', enabled='false'))
        assert result.status_code == 200
        assert 'owner-skill' in server.disabled_skills


@pytest.mark.parametrize('provider', ['skills_sh', 'skillhub'])
@pytest.mark.parametrize('action', ['search', 'trending'])
@pytest.mark.parametrize('entry', ['direct', 'gateway'])
async def test_marketplace_annotations_keep_the_configuration_from_request_entry(owned, monkeypatch, provider, action, entry):
    server, first, second = owned
    row = {'source': 'team/research', 'skillId': 'owner-skill'} if provider == 'skills_sh' else {'slug': 'owner-skill'}
    key = 'results' if provider == 'skillhub' and action == 'search' else 'skills'
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {key: [row]})

    async def get(*args, **kwargs):
        monkeypatch.setattr('cirno_core.config.loader._current_config_path', second)
        return response

    @asynccontextmanager
    async def client():
        yield SimpleNamespace(get=AsyncMock(side_effect=get))

    monkeypatch.setattr(market, '_skills_client' if provider == 'skills_sh' else '_skillhub_client', client)
    if entry == 'gateway':
        monkeypatch.setattr('cirno_core.config.loader._current_config_path', second)
        query = request()
        query.path = f'/v0/skills/{action}?q=owner&provider={provider}'
        handler = server.skills_routes._handle_webui_skills_search if action == 'search' else server.skills_routes._handle_webui_skills_trending
        response = await handler(query)
        assert response.status_code == 200
        result = json.loads(response.body)
    elif action == 'search':
        result = await market.search_marketplace_skills('owner', server.skills_workspace_path, provider=provider, home_path=server.settings.home_path)
    else:
        result = await market.trending_marketplace_skills(server.skills_workspace_path, provider=provider, home_path=server.settings.home_path)
    assert result['skills'][0]['installed'] is True


@pytest.mark.parametrize('provider', ['skills_sh', 'skillhub'])
async def test_gateway_install_recognizes_its_enabled_plugin_without_installing_anything(owned, monkeypatch, provider):
    server, first, second = owned
    monkeypatch.setattr('cirno_core.config.loader._current_config_path', second)
    monkeypatch.setattr(market.shutil, 'which', lambda command: None)
    monkeypatch.setattr(market, '_skillhub_client', Mock(side_effect=AssertionError('must not contact SkillHub')))
    monkeypatch.setattr(market.asyncio, 'create_subprocess_exec', AsyncMock(side_effect=AssertionError('must not launch npx')))
    response = await server.skills_routes._handle_webui_skill_install(request(provider=provider,
        source='team/research', skill='owner-skill', version='1.0'))
    assert response.status_code == 200
    assert json.loads(response.body)['last_action']['already_installed'] is True
