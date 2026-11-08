"""Upgrading personal channels retires old approvals without losing inbox actions."""

import json
import sqlite3
from contextlib import closing

import pytest
from cirno_core.notifications.inbox import NotificationInbox
from cirno_server.maintenance.migrations.plan import MigrationPlan
from cirno_server.maintenance.migrations.registry import migrate_instance
from cirno_server.maintenance.migrations.v016 import Import016


def seed_inbox(instance):
    inbox = NotificationInbox(instance / "state")
    inbox.record("pairing:alice", "operations", "pairing", status="pending", body="Old access request", data={"channel": "telegram"})
    inbox.record("approval:run", "operations", "approval", status="pending", body="Run scientific analysis", data={"command": "python analyze.py"})
    inbox.record("report:research", "conversations", "report", body="Result verified")
    return inbox


def test_migration_archives_old_access_and_preserves_other_pending_actions(released):
    instance, _, config = released
    inbox = seed_inbox(instance)
    old_store = instance / "state/pairing.json"
    old_store.write_text('{"approved":{"telegram":["alice"]}}')
    original = old_store.read_bytes()
    attachment = inbox.path.parent / "receipt.txt"
    attachment.write_text("A retained notification artifact")

    assert migrate_instance(config)
    items = {row["id"]: row for row in inbox.list()["items"]}
    retired = items["pairing:alice"]
    assert (retired["category"], retired["kind"], retired["status"]) == ("system", "migration", "resolved")
    assert "Settings → Telegram" in retired["body"]
    assert items["approval:run"]["status"] == "pending"
    assert items["approval:run"]["data"] == {"command": "python analyze.py"}
    assert items["report:research"]["body"] == "Result verified"
    assert attachment.read_text() == "A retained notification artifact"
    assert "pairing:alice" not in {row["id"] for row in inbox.telegram_pending()}
    assert "approval:run" in {row["id"] for row in inbox.telegram_pending()}
    inbox.queue_pending_actions()
    assert "pairing:alice" not in {row["id"] for row in inbox.telegram_pending()}
    assert not old_store.exists()
    root = instance / "state/migrations/0.1.6-to-0.2.0"
    assert json.loads((root / "report.json").read_text())["retired_pairing_notices"] == 1
    assert any(p.read_bytes() == original for p in (root / "originals").glob("retired-*") if p.is_file())
    [archived] = (root / "originals").rglob("inbox.sqlite3")
    with closing(sqlite3.connect(archived)) as db:
        assert db.execute("SELECT kind,status,body FROM notices WHERE id='pairing:alice'").fetchone() == ("pairing", "pending", "Old access request")
    notice_ids = {row["id"] for row in inbox.list()["items"]}
    assert not migrate_instance(config)
    assert {row["id"] for row in inbox.list()["items"]} == notice_ids


def test_preparation_failure_keeps_original_inbox_and_pairing_store(released, monkeypatch):
    instance, _, config = released
    inbox = seed_inbox(instance)
    old_store = instance / "state/pairing.json"
    old_store.write_text("original access approvals")
    before = inbox.path.read_bytes(), config.read_bytes()

    def fail_validation(*args):
        raise ValueError("Invalid configuration fixture")

    monkeypatch.setattr("cirno_server.maintenance.migrations.v016.import_configuration", fail_validation)
    with pytest.raises(ValueError, match="Invalid configuration fixture"):
        migrate_instance(config)
    assert (inbox.path.read_bytes(), config.read_bytes()) == before
    assert old_store.read_text() == "original access approvals"
    assert {row["id"]: row["status"] for row in inbox.list()["items"]}["pairing:alice"] == "pending"


def test_staged_inbox_includes_committed_wal_and_resumes_before_other_stores(released):
    instance, _, config = released
    inbox = seed_inbox(instance)
    root = instance / "state/migrations/0.1.6-to-0.2.0"
    with closing(sqlite3.connect(inbox.path)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("UPDATE notices SET body='Latest committed report' WHERE id='report:research'")
        writer.commit()
        assert inbox.path.with_name("inbox.sqlite3-wal").stat().st_size > 0
        Import016().prepare(config, json.loads(config.read_text()), root)
        # Preparation only snapshots; source handles close before offline apply.
        assert {row["id"]: row for row in inbox.list()["items"]}["pairing:alice"]["status"] == "pending"
    MigrationPlan.load(root).apply()
    items = {row["id"]: row for row in inbox.list()["items"]}
    assert items["report:research"]["body"] == "Latest committed report"
    assert items["pairing:alice"]["status"] == "resolved"
    with closing(sqlite3.connect(inbox.path)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
