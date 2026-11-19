"""Skill routes use the captured Home, and installer cancellation owns its fake process."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.config.home import set_instance_path
from cirno_server.webui.http.skills import SkillsRoutes
from cirno_server.webui.settings.services import WebUISettingsServices
from cirno_server.webui.skills_marketplace import install_marketplace_skill
from websockets.datastructures import Headers


def skill(home, text):
    directory = home / 'skills' / 'owned-fixture'
    directory.mkdir(parents=True)
    (directory / 'SKILL.md').write_text(f'---\nname: owned-fixture\ndescription: {text}\n---\n{text}\n')
    return directory


def fixture(tmp_path):
    home, other = tmp_path / 'owned' / 'home', tmp_path / 'other' / 'home'
    set_instance_path(home.parent)
    settings = WebUISettingsServices.create(tmp_path / 'external' / 'server.json')
    server = SimpleNamespace(settings=settings, skills_workspace_path=tmp_path / 'workspace', disabled_skills=set(),
        check_api_token=lambda request: True, skill_state_action=None, _skill_install_lock=asyncio.Lock())
    server.skills_routes = SkillsRoutes(server)
    return server, home, other


@pytest.mark.parametrize('operation', ['catalog', 'detail', 'delete', 'disable'])
async def test_skill_route_uses_the_captured_home(tmp_path, operation):
    server, home, other = fixture(tmp_path)
    owned = skill(home, 'Owned instructions')
    if operation != 'disable':
        ambient = skill(other, 'Other instructions')
    set_instance_path(other.parent)
    request = SimpleNamespace(path='/v0/skills', headers=Headers(), _cirno_webui_mutation_request=True,
        _cirno_webui_mutation_payload={'name': 'owned-fixture', 'enabled': 'false'})
    if operation == 'catalog':
        result = await server.skills_routes._load_webui_skills()
        assert next(item for item in result['skills'] if item['name'] == 'owned-fixture')['description'] == 'Owned instructions'
    elif operation == 'detail':
        response = await server.skills_routes._handle_webui_skill_detail(request, 'owned-fixture')
        assert response.status_code == 200
        assert 'Owned instructions' in json.loads(response.body)['raw_markdown']
    elif operation == 'delete':
        response = await server.skills_routes._handle_webui_skill_delete(request)
        assert response.status_code == 200
        assert not owned.exists()
        assert ambient.is_dir()
        assert list((home / 'skills-history' / 'owned-fixture').glob('*/SKILL.md'))
        assert not (other / 'skills-history').exists()
    else:
        response = await server.skills_routes._handle_webui_skill_update(request)
        assert response.status_code == 200
        assert 'owned-fixture' in server.disabled_skills


async def test_cancelled_installer_kills_and_drains_its_process_before_returning(tmp_path, monkeypatch):
    from cirno_server.webui import skills_marketplace as module
    set_instance_path(tmp_path / 'owned')
    entered, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    kills = []
    process = SimpleNamespace(returncode=None, pid=987654)
    def kill():
        kills.append(True)
        process.returncode = -9
    async def communicate():
        if process.returncode is None:
            entered.set()
            await asyncio.Event().wait()
        cleanup.set()
        await release.wait()
        return b'', None
    async def drain(_size):
        cleanup.set()
        await release.wait()
        return b''
    process.kill, process.communicate = kill, communicate
    process.stdout, process.stderr = SimpleNamespace(read=drain), None
    process.wait = AsyncMock(return_value=-9)
    monkeypatch.setattr('cirno_core.utils.subprocess.os.killpg', lambda *_: kill(), raising=False)
    monkeypatch.setattr(module.shutil, 'which', lambda _: '/fake/npx')
    monkeypatch.setattr(module.asyncio, 'create_subprocess_exec', AsyncMock(return_value=process))
    task = asyncio.create_task(install_marketplace_skill('fixture/tools', 'install-fixture', tmp_path / 'workspace'))
    try:
        async with asyncio.timeout(2):
            await entered.wait()
        task.cancel()
        for _ in range(5):
            await asyncio.sleep(0)
        assert kills == [True]
        assert cleanup.is_set() and not task.done()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize('operation', ['disable', 'delete'])
async def test_skill_mutations_leave_the_gateway_loop_responsive(tmp_path, monkeypatch, operation):
    from threading import Event

    from cirno_server.webui.http import skills as module
    server, home, _ = fixture(tmp_path)
    loop = asyncio.get_running_loop()
    def mutate(*args, disabled_skills, home_path, **kwargs):
        assert home_path == home
        responsive = Event()
        loop.call_soon_threadsafe(responsive.set)
        assert responsive.wait(1), 'Skill disk operation blocked the gateway'
        disabled_skills.add('owned-fixture')
        return {'name': 'owned-fixture', 'deleted': operation == 'delete'}
    monkeypatch.setattr(module, 'set_webui_skill_enabled' if operation == 'disable' else 'delete_webui_skill', mutate)
    monkeypatch.setattr(server.skills_routes, '_load_webui_skills', AsyncMock(return_value={'skills': []}))
    request = SimpleNamespace(path='/v0/skills', headers=Headers(), _cirno_webui_mutation_request=True,
        _cirno_webui_mutation_payload={'name': 'owned-fixture', 'enabled': 'false'})
    response = await (server.skills_routes._handle_webui_skill_update(request) if operation == 'disable'
                      else server.skills_routes._handle_webui_skill_delete(request))
    assert response.status_code == 200
    assert 'owned-fixture' in server.disabled_skills


@pytest.mark.parametrize('operation', ['disable', 'delete'])
async def test_cancelled_skill_mutation_finishes_runtime_publication(tmp_path, monkeypatch, operation):
    from threading import Event

    from cirno_server.webui.http import skills as module
    server, home, _ = fixture(tmp_path)
    entered, release = Event(), Event()
    applied = []
    server.skill_state_action = lambda disabled: applied.append(disabled)
    def mutate(*args, disabled_skills, home_path, **kwargs):
        assert home_path == home
        entered.set()
        assert release.wait(2)
        disabled_skills.add('owned-fixture')
        return {'name': 'owned-fixture', 'deleted': operation == 'delete'}
    monkeypatch.setattr(module, 'set_webui_skill_enabled' if operation == 'disable' else 'delete_webui_skill', mutate)
    request = SimpleNamespace(path='/v0/skills', headers=Headers(), _cirno_webui_mutation_request=True,
        _cirno_webui_mutation_payload={'name': 'owned-fixture', 'enabled': 'false'})
    task = asyncio.create_task(server.skills_routes._handle_webui_skill_update(request) if operation == 'disable'
                               else server.skills_routes._handle_webui_skill_delete(request))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert server.disabled_skills == set()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert server.disabled_skills == {'owned-fixture'}
        assert applied == [{'owned-fixture'}]
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize('provider', ['skills_sh', 'skillhub'])
@pytest.mark.parametrize('query', ['search', 'trending'])
@pytest.mark.parametrize('explicit', [False, True])
async def test_marketplace_installed_state_stays_in_its_home_across_lookup(tmp_path, monkeypatch, provider, query, explicit):
    from cirno_server.webui import skills_marketplace as module
    _, home, other = fixture(tmp_path)
    skill(home, 'Owned instructions')
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            row = {'skillId': 'owned-fixture', 'source': 'fixture/tools', 'slug': 'owned-fixture', 'name': 'Fixture'}
            return {'skills': [row], 'results': [row]}
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, *args, **kwargs):
            set_instance_path(other.parent)
            return Response()
    monkeypatch.setattr(module, '_skills_client', Client)
    monkeypatch.setattr(module, '_skillhub_client', Client)
    if explicit:
        set_instance_path(other.parent)
    arguments = {'provider': provider, **({'home_path': home} if explicit else {})}
    result = await (module.search_marketplace_skills('fixture', tmp_path / 'workspace', **arguments) if query == 'search'
                    else module.trending_marketplace_skills(tmp_path / 'workspace', **arguments))
    assert len(result['skills']) == 1 and result['skills'][0]['installed']


async def test_installer_timeout_keeps_the_timeout_error_after_process_cleanup(tmp_path, monkeypatch):
    from cirno_server.webui import skills_marketplace as module
    set_instance_path(tmp_path / 'owned')
    process = SimpleNamespace(pid=987655, returncode=None, stdout=None, stderr=None, wait=AsyncMock(return_value=-9))
    process.communicate = AsyncMock(side_effect=AssertionError('Zero timeout should not enter communicate'))
    signals = []
    def killed(*args):
        signals.append(args)
        process.returncode = -9
    monkeypatch.setattr('cirno_core.utils.subprocess.os.killpg', killed, raising=False)
    process.kill = lambda: killed(process.pid)
    monkeypatch.setattr(module.shutil, 'which', lambda _: '/fake/npx')
    monkeypatch.setattr(module.asyncio, 'create_subprocess_exec', AsyncMock(return_value=process))
    monkeypatch.setattr(module, '_INSTALL_TIMEOUT_SECONDS', 0)
    with pytest.raises(module.SkillsMarketplaceError) as error:
        await install_marketplace_skill('fixture/tools', 'timeout-fixture', tmp_path / 'workspace')
    assert error.value.status == 504
    assert len(signals) == 1
    process.wait.assert_awaited_once()


@pytest.mark.parametrize('provider', ['skills_sh', 'skillhub'])
async def test_bound_existing_skill_skips_installation_before_any_external_work(tmp_path, monkeypatch, provider):
    from cirno_server.webui import skills_marketplace as module
    _, home, other = fixture(tmp_path)
    skill(home, 'Owned instructions')
    set_instance_path(other.parent)
    def forbidden(*args, **kwargs):
        pytest.fail('An existing owned skill must not start external work')
    monkeypatch.setattr(module, '_skills_client', forbidden)
    monkeypatch.setattr(module, '_skillhub_client', forbidden)
    monkeypatch.setattr(module.asyncio, 'create_subprocess_exec', forbidden)
    result = await install_marketplace_skill('fixture/tools', 'owned-fixture', tmp_path / 'workspace', provider=provider, home_path=home)
    assert result['already_installed'] is True
