"""SkillHub archive work uses tiny synthetic archives and fake network clients only."""

import asyncio
import hashlib
import io
import threading
import zipfile
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from cirno_server.webui import skills_marketplace as module


@pytest.fixture
def install(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    content = b'---\nname: archive-fixture\ndescription: Local fixture\n---\n'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('SKILL.md', content)
        archive.writestr('scripts/example.py', b'print("fixture")\n')
    entries = [('SKILL.md', content), ('scripts/example.py', b'print("fixture")\n')]
    fingerprint = hashlib.sha256(''.join(f'{name}:{hashlib.sha256(data).hexdigest()}\n' for name, data in sorted(entries)).encode()).hexdigest()

    @asynccontextmanager
    async def client():
        yield object()

    async def download(_client, _skill, _version, destination):
        destination.write_bytes(buffer.getvalue())

    monkeypatch.setattr(module, '_skillhub_client', client)
    monkeypatch.setattr(module, '_skillhub_signature', AsyncMock(return_value={'content_hash': fingerprint}))
    downloader = AsyncMock(side_effect=download)
    monkeypatch.setattr(module, '_download_skillhub_archive', downloader)

    async def run():
        return await module.install_marketplace_skill('', 'archive-fixture', tmp_path / 'workspace', provider='skillhub', version='1.0', home_path=home)

    return run, home / 'skills' / 'archive-fixture', downloader


async def test_archive_hash_and_extraction_do_not_block_the_event_loop(install, monkeypatch):
    run, target, _ = install
    loop_thread = threading.get_ident()
    observed = []
    for name in ('_validate_skillhub_archive', '_extract_skillhub_archive'):
        original = getattr(module, name)
        def observe(*args, original=original):
            observed.append(threading.get_ident())
            return original(*args)
        monkeypatch.setattr(module, name, observe)
    result = await run()
    assert result['installed'] is True
    assert target.joinpath('SKILL.md').is_file()
    assert len(observed) == 2
    assert all(thread != loop_thread for thread in observed)


@pytest.mark.parametrize('kind', ['file', 'directory'])
async def test_an_occupied_non_skill_target_is_not_reported_as_installed(install, kind):
    run, target, downloader = install
    target.parent.mkdir(parents=True)
    if kind == 'file':
        target.write_text('User-owned content')
    else:
        target.mkdir()
    with pytest.raises(module.SkillsMarketplaceError) as caught:
        await run()
    assert caught.value.status == 409
    if kind == 'file':
        assert target.read_text() == 'User-owned content'
    else:
        assert list(target.iterdir()) == []
    downloader.assert_not_awaited()


@pytest.mark.parametrize('phase', ['_validate_skillhub_archive', '_extract_skillhub_archive'])
async def test_cancellation_retains_staging_until_archive_commit_settles(install, monkeypatch, phase):
    run, target, _ = install
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    original = getattr(module, phase)
    temporary = []

    def delayed(*args):
        temporary.append(args[0].parent)
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(2), 'test did not release the archive worker'
        assert args[0].exists(), 'staging was cleaned while the worker still owned it'
        return original(*args)

    monkeypatch.setattr(module, phase, delayed)
    task = asyncio.create_task(run())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert temporary[0].exists()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert target.joinpath('SKILL.md').is_file()
    assert not temporary[0].exists()
    assert not list(target.parent.glob('.skillhub-install-*'))


async def test_bad_fingerprint_leaves_no_installed_or_staged_files(install, monkeypatch):
    run, target, _ = install
    monkeypatch.setattr(module, '_skillhub_signature', AsyncMock(return_value={'content_hash': '0' * 64}))
    with pytest.raises(module.SkillsMarketplaceError, match='fingerprint did not match') as caught:
        await run()
    assert caught.value.status == 502
    assert not target.exists()
    assert not list(target.parent.glob('.skillhub-install-*'))


async def test_download_cancellation_removes_partial_staging_without_publication(install):
    run, target, download = install
    entered = asyncio.Event()
    temporary = []

    async def partial(_client, _skill, _version, destination):
        destination.write_bytes(b'partial archive')
        temporary.append(destination.parent)
        entered.set()
        await asyncio.Event().wait()

    download.side_effect = partial
    task = asyncio.create_task(run())
    await asyncio.wait_for(entered.wait(), 1)
    assert temporary[0].is_dir()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not target.exists()
    assert not temporary[0].exists()


async def test_a_target_created_during_download_is_preserved_and_reports_conflict(install, monkeypatch):
    run, target, download = install
    original = download.side_effect

    async def collision(*args):
        await original(*args)
        target.mkdir()
        target.joinpath('owner.txt').write_text('keep me')

    download.side_effect = collision
    with pytest.raises(module.SkillsMarketplaceError) as caught:
        await run()
    assert caught.value.status == 409
    assert target.joinpath('owner.txt').read_text() == 'keep me'
    assert not target.joinpath('SKILL.md').exists()
    assert not list(target.parent.glob('.skillhub-install-*'))
