"""Home remains separate from --config and bound to the gateway that owns a request."""

import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.config.home import set_instance_path
from cirno_server.webui.http.handler import ServerHTTPHandler
from cirno_server.webui.http_utils import http_json_response
from cirno_server.webui.settings.profiles import profile_payload
from cirno_server.webui.settings.routes import WebUISettingsRouter
from cirno_server.webui.settings.services import WebUISettingsServices
from websockets.datastructures import Headers


def settings(tmp_path):
    root = tmp_path / 'owned'
    set_instance_path(root)
    services = WebUISettingsServices.create(tmp_path / 'separate-config' / 'server.json')
    return services, root / 'home', tmp_path / 'ambient' / 'home'


def request(payload, path):
    return SimpleNamespace(path=path, headers=Headers(), _cirno_webui_mutation_request=True,
                           _cirno_webui_mutation_payload=payload)


def profile_router(services):
    return WebUISettingsRouter(settings=services, bus=MessageBus(), logger=SimpleNamespace(exception=lambda *a: None, warning=lambda *a: None),
        check_api_token=lambda request: True, parse_query=lambda path: parse_qs(urlsplit(path).query),
        json_response=http_json_response, error_response=lambda status, message: http_json_response({'error': message}, status=status))


@pytest.mark.parametrize('action', ['read', 'update'])
async def test_profile_route_retains_home_after_global_selection_changes(tmp_path, action):
    services, home, other = settings(tmp_path)
    for directory in [home, other]:
        directory.mkdir(parents=True)
        (directory / 'SOUL.md').write_text('Original')
    before = profile_payload('soul')
    if action == 'read':
        (other / 'SOUL.md').write_text('Wrong Home')
    set_instance_path(other.parent)
    path = f'/v0/settings/profile/{action}'
    values = {'name': 'soul', 'content': 'Owned edit', 'revision': before['revision']}
    response = await profile_router(services).dispatch(None, request(values, path), path)
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body['content'] == ('Original' if action == 'read' else 'Owned edit')
    assert (home / 'SOUL.md').read_text() == ('Original' if action == 'read' else 'Owned edit')
    assert (other / 'SOUL.md').read_text() == ('Wrong Home' if action == 'read' else 'Original')


@pytest.mark.parametrize('action', ['memory.read', 'skills.history'])
async def test_instance_dispatch_retains_its_home_for_memory_and_skill_history(tmp_path, monkeypatch, action):
    services, home, other = settings(tmp_path)
    selected = []
    class Repository:
        def __init__(self, path):
            selected.append(path)
        def sync_profiles(self):
            pass
        def read(self, *args, **kwargs):
            return {'content': 'fixture'}
    def inspect(name, operation, path):
        selected.append(path)
        return {'versions': []}
    monkeypatch.setattr('cirno_memory.repository.MemoryRepository', Repository)
    monkeypatch.setattr('cirno_server.webui.instance_api.inspect_skill', inspect)
    server = SimpleNamespace(config=SimpleNamespace(token_issue_path=None), check_api_token=lambda request: True,
        settings_routes=SimpleNamespace(settings=services), session_manager=None, bus=None)
    set_instance_path(other.parent)
    path = '/v0/instance'
    response = await ServerHTTPHandler._dispatch_resolved(server, None, request({'action': action, 'values': {'id': 'fixture', 'name': 'fixture'}}, path), path)
    assert response.status_code == 200
    assert selected == [home]
