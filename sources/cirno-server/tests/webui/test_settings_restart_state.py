"""Restart decisions compare runtime values rather than masked browser DTOs."""

from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.config.home import set_instance_path
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_server.webui.settings.routes import WebUISettingsRouter
from cirno_server.webui.settings.services import WebUISettingsServices
from websockets.datastructures import Headers
from websockets.http11 import Request


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


async def test_reverting_network_flag_clears_restart_without_reverting_live_default_access(router):
    path = '/v0/settings/network-safety/update'

    async def save(payload):
        request = Request(path, Headers())
        request._cirno_webui_mutation_request = True
        request._cirno_webui_mutation_payload = payload
        return await router.dispatch(None, request, path)

    changed = await save({'webui_allow_local_service_access': False})
    assert changed['requires_restart'] is True
    live_only = await save({'webui_default_access_mode': 'full'})
    assert live_only['requires_restart'] is True
    assert live_only['advanced']['webui_default_access_mode'] == 'full'
    restored = await save({'webui_allow_local_service_access': True})
    assert restored['requires_restart'] is False
    assert restored['restart_required_sections'] == []
    assert restored['advanced']['webui_default_access_mode'] == 'full'


async def test_partially_saved_network_error_still_records_restart_requirement(router, monkeypatch):
    from cirno_server.webui.settings import api

    def fail(*args, **kwargs):
        raise OSError('locked file')

    path = '/v0/settings/network-safety/update'
    request = Request(path, Headers())
    request._cirno_webui_mutation_request = True
    request._cirno_webui_mutation_payload = {
        'webui_allow_local_service_access': False, 'webui_default_access_mode': 'full',
    }
    with monkeypatch.context() as failed_disk:
        failed_disk.setattr(api, 'write_webui_default_access_mode', fail)
        failed_disk.setattr(api, 'atomic_write_bytes', fail)
        error = await router.dispatch(None, request, path)
    assert error['status'] == 500
    assert 'rollback was incomplete' in error['error']
    read = Request('/v0/settings', Headers())
    payload = await router.dispatch(None, read, read.path)
    assert payload['advanced']['webui_allow_local_service_access'] is False
    assert payload['requires_restart'] is True
    assert payload['restart_required_sections'] == ['runtime']

    request._cirno_webui_mutation_payload = {'webui_allow_local_service_access': True}
    restored = await router.dispatch(None, request, path)
    assert restored['requires_restart'] is False


@pytest.mark.parametrize("domain", ["network", "web-search"])
async def test_cancelled_capability_route_keeps_restart_state(router, monkeypatch, domain):
    import asyncio
    import threading

    from cirno_server.webui.settings import api

    committed, release, finished = (threading.Event() for _ in range(3))
    save = api._save_settings_config

    def delayed_save(config, path):
        save(config, path)
        committed.set()
        try:
            assert release.wait(3)
        finally:
            finished.set()

    monkeypatch.setattr(api, "_save_settings_config", delayed_save)
    path = '/v0/settings/network-safety/update' if domain == 'network' else '/v0/settings/web-search/update'
    request = Request(path, Headers())
    request._cirno_webui_mutation_request = True
    request._cirno_webui_mutation_payload = (
        {'webui_allow_local_service_access': False} if domain == 'network'
        else {'provider': 'duckduckgo', 'use_jina_reader': False}
    )
    task = asyncio.create_task(router.dispatch(None, request, path))
    try:
        assert await asyncio.to_thread(committed.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        read = Request('/v0/settings', Headers())
        payload = await router.dispatch(None, read, read.path)
        assert payload['requires_restart'] is True
        assert payload['restart_required_sections'] == ['runtime' if domain == 'network' else 'browser']
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 2)
