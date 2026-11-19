"""Backup discovery and accepted cancellation retain their original owners."""

import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.config.home import set_instance_path
from cirno_core.config.loader import set_config_path
from cirno_server.backup.archive import Backups
from cirno_server.backup.http import BackupHTTP
from cirno_server.webui.workspaces import remember_webui_project


@pytest.mark.parametrize("resource", ["home", "preferences", "default-workspace"])
def test_backup_recommendations_keep_the_captured_home_and_instance_preferences(tmp_path, monkeypatch, resource):
    first, second, home = tmp_path / "first", tmp_path / "second", tmp_path / "separate-home"
    fake_user = tmp_path / "host-user"
    fake_user.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_user))
    monkeypatch.delenv("HOMEBREW_PREFIX", raising=False)
    for root in (first, second):
        root.mkdir()
        (root / "workspace").mkdir()
        (root / "config.json").write_text(json.dumps({"agents": {"defaults": {"workspace": str(root / "workspace")}}}))
    (home / "home").mkdir(parents=True)
    (home / "workspace").mkdir()
    (second / "home").mkdir()
    folders = [tmp_path / "original-project", tmp_path / "unrelated-project"]
    for folder in folders:
        folder.mkdir()
    set_instance_path(home)
    set_config_path(first / "config.json")
    remember_webui_project(folders[0])
    if resource == "default-workspace":
        (first / "config.json").write_text("{}")
    backup = Backups(first / "config.json")
    set_instance_path(second)
    set_config_path(second / "config.json")
    remember_webui_project(folders[1])
    result = backup.recommendations()
    paths = {item["path"] for item in result["recommended"]}
    if resource == "home":
        assert str(home / "home") in paths and str(second / "home") not in paths
        assert str(home / "home") in result["selected"]
    elif resource == "preferences":
        assert str(folders[0]) in paths and str(folders[1]) not in paths
    else:
        assert str(home / "workspace") in paths and str(second / "workspace") not in paths


async def test_cancelling_preview_cleanup_waits_before_releasing_backup_lock(tmp_path, monkeypatch):
    service = BackupHTTP(tmp_path / "config.json", SimpleNamespace(authorized=lambda _: True), MessageBus(), None)
    identifier = "a" * 32
    stage = service.archive.store / "staging" / identifier
    stage.mkdir(parents=True)
    service.archive.store.joinpath("restore-plan.json").write_text(json.dumps({"id": identifier}))
    entered, release, finished = asyncio.Event(), threading.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    import shutil
    original = shutil.rmtree

    def cleanup(path):
        loop.call_soon_threadsafe(entered.set)
        try:
            assert release.wait(2)
            return original(path)
        finally:
            finished.set()

    monkeypatch.setattr("cirno_server.backup.http.shutil.rmtree", cleanup)

    async def chunks(_size):
        yield json.dumps({"id": identifier}).encode()

    request = SimpleNamespace(method="POST", path="/v0/backups/cancel", headers={"Authorization": "Bearer owner"},
                              content=SimpleNamespace(iter_chunked=chunks))
    task = asyncio.create_task(service.handle(request))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.01)
        assert not done and service.lock.locked(), "Cleanup escaped its backup operation owner"
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 1)
    assert task.cancelled()
    assert not stage.exists() and not service.archive.store.joinpath("restore-plan.json").exists()


@pytest.mark.parametrize("identifier", [False, 0, ""])
async def test_invalid_cancel_id_cannot_cancel_a_pending_restore(tmp_path, identifier):
    service = BackupHTTP(tmp_path / "config.json", SimpleNamespace(authorized=lambda _: True), MessageBus(), None)
    service.archive.store.mkdir(parents=True)
    plan = service.archive.store / "restore-plan.json"
    plan.write_text(json.dumps({"id": "a" * 32}))

    async def chunks(_size):
        yield json.dumps({"id": identifier}).encode()

    request = SimpleNamespace(method="POST", path="/v0/backups/cancel", headers={"Authorization": "Bearer owner"},
                              content=SimpleNamespace(iter_chunked=chunks))
    result = await service.handle(request)
    assert result.status == 400
    assert json.loads(plan.read_text()) == {"id": "a" * 32}


def test_explicit_environment_workspace_still_overrides_the_captured_default(tmp_path, monkeypatch):
    root, workspace = tmp_path / "instance", tmp_path / "configured-workspace"
    root.mkdir()
    workspace.mkdir()
    root.joinpath("config.json").write_text("{}")
    set_instance_path(root)
    backup = Backups(root / "config.json")
    monkeypatch.setenv("CIRNO_AGENTS__DEFAULTS__WORKSPACE", str(workspace))
    paths = {item["path"] for item in backup.recommendations()["recommended"]}
    assert str(workspace) in paths
