"""Restart decisions compare runtime values rather than masked browser DTOs."""

from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from websockets.datastructures import Headers
from websockets.http11 import Request

from cirno_core.bus.queue import MessageBus
from cirno_core.config.home import set_instance_path
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_server.webui.settings.routes import WebUISettingsRouter
from cirno_server.webui.settings.services import WebUISettingsServices


@pytest.fixture
def router(tmp_path):
    set_instance_path(tmp_path)
    config = Config()
    config.agents.defaults.memory.embedding_api_key = 'initial-secret'
    path = tmp_path / 'config.json'
    save_config(config, path)
    instance = WebUISettingsRouter(
        settings=WebUISettingsServices.create(path), bus=MessageBus(), logger=MagicMock(),
        check_api_token=lambda request: True,
        parse_query=lambda path: parse_qs(urlsplit(path).query),
        json_response=lambda payload: payload,
        error_response=lambda status, message: {'error': message, 'status': status},
    )
    yield instance
    set_instance_path(None)


async def update(router, values):
    path = '/v0/settings/runtime-config/update'
    request = Request(path, Headers())
    request._cirno_webui_mutation_request = True
    request._cirno_webui_mutation_payload = {'values': values}
    result = await router.dispatch(None, request, path)
    assert 'error' not in result
    return result


@pytest.mark.asyncio
async def test_rotating_masked_embedding_key_requires_restart_and_reverting_clears_it(router):
    key = 'agents.defaults.memory.embedding_api_key'
    first = await update(router, {key: 'replacement-secret'})
    assert first['requires_restart']
    assert first['restart_required_sections'] == ['runtime']
    assert 'replacement-secret' not in str(first)
    assert 'initial-secret' not in str(router._restart_baselines)
    assert 'replacement-secret' not in str(router._restart_baselines)
    restored = await update(router, {key: 'initial-secret'})
    assert not restored['requires_restart']
    assert restored['restart_required_sections'] == []


@pytest.mark.asyncio
async def test_hot_prompt_changes_do_not_prevent_reverting_restart_settings(router):
    timeout = 'network.request_timeout_s'
    prompt = 'agents.defaults.system_prompts.router'
    assert (await update(router, {timeout: 180}))['requires_restart']
    assert (await update(router, {prompt: 'New live instructions'}))['requires_restart']
    result = await update(router, {timeout: 120})
    assert not result['requires_restart']
    assert result['runtime_config'][prompt] == 'New live instructions'
