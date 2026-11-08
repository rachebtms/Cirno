"""Startup resumes committed offline work before treating missing config as fresh."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cirno_core import __version__
from cirno_server.maintenance.migrations.plan import MigrationPlan
from cirno_server.maintenance.migrations.registry import migrate_instance
from cirno_server.maintenance.startup import finish_pending_maintenance


def test_config_rename_interruption_recovers_without_new_owner_setup(released, released_store, monkeypatch):
    instance, workspace, path = released
    released_store(instance, workspace, "a" * 32)
    original = path.read_bytes()
    rename = Path.rename

    def fail_install(self, target):
        if self.name == "config.json" and self.parent.name == "staged":
            raise OSError("Injected interrupted config installation")
        return rename(self, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", fail_install)
        with pytest.raises(OSError, match="Injected interrupted"):
            migrate_instance(path)
    assert not path.exists()
    assert (instance / "state/migrations/0.1.6-to-0.2.0/originals/target-1").read_bytes() == original
    finish_pending_maintenance(path)
    assert json.loads(path.read_text())["lastRunVersion"] == "0.2.0"
    assert (instance / "state/sessions/instance/sessions.sqlite3").exists()
    assert not (workspace / ".cirno").exists()
    assert migrate_instance(path)
    assert json.loads(path.read_text())["lastRunVersion"] == __version__
    assert not migrate_instance(path)


def test_partial_retirement_keeps_original_until_copy_completes(tmp_path, monkeypatch):
    from cirno_server.maintenance.migrations import plan as module

    source = tmp_path / "old-workspace/cron"
    source.mkdir(parents=True)
    (source / "jobs.json").write_text("jobs")
    plan = MigrationPlan(tmp_path / "migration")
    plan.retire(source)
    plan.save()
    copy = module.copy_path

    def fail_copy(source, target):
        target.mkdir(parents=True)
        (target / "partial").touch()
        raise OSError("Disk full")

    monkeypatch.setattr(module, "copy_path", fail_copy)
    with pytest.raises(OSError, match="Disk full"):
        plan.apply()
    assert (source / "jobs.json").read_text() == "jobs"
    monkeypatch.setattr(module, "copy_path", copy)
    MigrationPlan.load(plan.root).apply()
    assert not source.exists()
    assert (plan.root / "originals/retired-0/jobs.json").read_text() == "jobs"
    assert not (plan.root / "originals/retired-0/partial").exists()
    MigrationPlan.load(plan.root).apply()


def test_other_live_server_prevents_migration(released, monkeypatch):
    from cirno_server.maintenance import startup

    instance, _, path = released
    run = instance / "state/run"
    run.mkdir(parents=True)
    (run / "gateway.other.json").write_text("{}")
    monkeypatch.setattr(startup.ServerRuntime, "status", lambda self: SimpleNamespace(running=True, pid=999999))
    previous = path.read_bytes()
    with pytest.raises(ValueError, match="Stop Cirno process 999999"):
        migrate_instance(path)
    assert path.read_bytes() == previous
    assert not (instance / "state/migrations").exists()
