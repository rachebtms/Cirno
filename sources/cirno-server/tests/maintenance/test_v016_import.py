"""Migration preserves released conversations and moves only instance-owned artifacts."""

import json
import sqlite3
from contextlib import closing

import pytest
from cirno_core import __version__
from cirno_core.config.loader import load_config
from cirno_core.session.manager import SessionManager
from cirno_server.maintenance.migrations.registry import migrate_instance
from cirno_server.webui.auth.store import AccountStore



def read_json(path):
    return json.loads(path.read_text())


def test_released_instance_imports_history_settings_and_automation_state(released, released_store):
    instance, workspace, path = released
    source = released_store(instance, workspace, "a" * 32, text="研究结果\n" * 20_000)
    originals = {str(item.relative_to(instance)): item.read_bytes() for item in instance.rglob("*") if item.is_file()}
    for kind, filename, key, identifier in (("cron", "jobs.json", "jobs", "job1"), ("triggers", "triggers.json", "triggers", "TRIGGER1")):
        root = workspace / kind
        root.mkdir()
        (root / filename).write_text(json.dumps({"version": 1, key: [{"id": identifier, "sessionKey": "websocket:research"}]}))
        (root / "runs").mkdir()
        (root / "runs" / "completed.json").write_text('{"status":"ok"}')
    assert migrate_instance(path)
    assert read_json(path)["lastRunVersion"] == __version__
    assert load_config(path).model_presets["research"].display_name == "research"
    store = instance / "state/sessions/instance"
    sessions = SessionManager(workspace, sessions_root=store.parent)
    session = sessions.get_existing("websocket:research")
    assert session.messages[0]["content"] == "研究结果\n" * 20_000
    assert session.metadata["runtime_checkpoint"]["iteration"] == 7
    assert session.metadata["pending_user_followups"][0]["content"] == "Keep going"
    with closing(sqlite3.connect(store / "sessions.sqlite3")) as db:
        assert db.execute("SELECT count(*) FROM history_entries").fetchone()[0] == 1
        assert db.execute("SELECT digest FROM inbox_receipts").fetchone()[0] == "digest"
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not source.exists()
    assert not (workspace / ".cirno").exists()
    for kind in ("cron", "triggers"):
        assert not (workspace / kind).exists()
        assert (instance / "state" / kind / "runs/completed.json").is_file()
    for name in ("home/SOUL.md", "home/memory/MEMORY.md", "home/skills/physics/SKILL.md", "state/webui-auth.sqlite3", "workspace/AGENTS.md", "workspace/result.md"):
        assert (instance / name).read_bytes() == originals[name]
    accounts = AccountStore(instance / "state/webui-auth.sqlite3")
    token = accounts.login("old-owner", "Old-owner-pass!")
    assert AccountStore(accounts.path).authenticated(token)
    archived = instance / "state/migrations/0.1.6-to-0.2.0/originals"
    assert any(item.read_bytes() == originals["config.json"] for item in archived.rglob("config.json")) or any(
        item.read_bytes() == originals["config.json"] for item in archived.glob("target-*") if item.is_file())
    assert not migrate_instance(path)
    assert SessionManager(instance / "another-workspace", sessions_root=store.parent).get_existing(session.key)


def test_colliding_conversations_are_retained_and_references_follow_their_store(released, released_store, tmp_path):
    instance, workspace, path = released
    released_store(instance, workspace, "a" * 32, text="Current research")
    other = tmp_path / "previous-workspace"
    source = released_store(instance, other, "b" * 32, text="Different research", parent="websocket:research")
    trigger_dir = other / "triggers"
    trigger_dir.mkdir()
    (trigger_dir / "triggers.json").write_text(json.dumps({"version": 1, "triggers": [{"id": "OLD", "sessionKey": "websocket:research", "channel": "websocket", "chatId": "research"}]}))
    assert migrate_instance(path)
    report = read_json(instance / "state/migrations/0.1.6-to-0.2.0/report.json")
    renamed = report["renamed"][0]["target"]
    sessions = SessionManager(workspace, sessions_root=instance / "state/sessions")
    assert sessions.get_existing("websocket:research").messages[0]["content"] == "Current research"
    imported = sessions.get_existing(renamed)
    assert imported.messages[0]["content"] == "Different research"
    assert imported.metadata["parent_session_key"] == renamed
    assert imported.metadata["runtime_checkpoint"]["session_key"] == renamed
    trigger = read_json(instance / "state/triggers/triggers.json")["triggers"][0]
    assert trigger["sessionKey"] == renamed
    assert trigger["chatId"] == renamed.removeprefix("websocket:")
    assert not source.exists()


def test_identical_database_copies_do_not_duplicate_conversations(released, released_store, tmp_path):
    import shutil
    instance, workspace, path = released
    first = released_store(instance, workspace, "a" * 32)
    copy = first.with_name("b" * 32)
    shutil.copytree(first, copy)
    assert migrate_instance(path)
    report = read_json(instance / "state/migrations/0.1.6-to-0.2.0/report.json")
    assert report["conversations"] == 1
    assert report["renamed"] == []


def test_corrupt_source_does_not_replace_any_live_data(released, released_store):
    instance, workspace, path = released
    source = released_store(instance, workspace, "a" * 32)
    (source / "sessions.sqlite3").write_bytes(b"Not SQLite")
    config = path.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        migrate_instance(path)
    assert path.read_bytes() == config
    assert (source / "sessions.sqlite3").read_bytes() == b"Not SQLite"
    assert not (instance / "state/sessions/instance").exists()
    assert not list((instance / "state/migrations").glob("*/plan.json"))


def test_unknown_config_version_is_rejected_without_changing_config(released, released_store):
    _, _, path = released
    data = read_json(path)
    data["lastRunVersion"] = "9.0.0"
    path.write_text(json.dumps(data))
    original = path.read_bytes()
    with pytest.raises(ValueError, match="No Cirno migration from 9.0.0"):
        migrate_instance(path)
    assert path.read_bytes() == original


def test_empty_canonical_directory_is_not_retired_after_install(released):
    instance, _, path = released
    final = instance / "state/sessions/instance"
    final.mkdir(parents=True)
    assert migrate_instance(path)
    assert (final / "sessions.sqlite3").exists()


def test_unconfigured_trigger_queues_are_moved_and_completion_is_notified_once(released):
    from cirno_core.notifications.inbox import NotificationInbox
    instance, workspace, path = released
    root = workspace / "triggers"
    for name in ("inbox", "processing", "failed", "runs"):
        (root / name).mkdir(parents=True)
    (root / ".lock").touch()
    assert migrate_instance(path)
    assert not root.exists()
    assert (instance / "state/triggers/inbox").is_dir()
    assert not migrate_instance(path)
    rows = NotificationInbox(instance / "state").list(category="system")["items"]
    assert len(rows) == 8
    assert all(row["kind"] == "migration" for row in rows)
    assert {row["data"]["from"] for row in rows} == {"0.1.6", "0.2.0", "0.2.1", "0.2.2", "0.2.3", "0.2.4", "0.2.5", "0.2.6"}


@pytest.mark.parametrize(("previous", "updated"), [("/", "/v0/ws"), ("/socket", "/v0/socket"), ("/api/socket", "/v0/socket"), ("/v0/custom", "/v0/custom")])
def test_endpoint_import_updates_public_url_and_token_path(released, previous, updated):
    from cirno_server.channels.websocket.config import WebSocketConfig
    _, _, path = released
    data = read_json(path)
    data["channels"] = {"websocket": {"path": previous, "publicWsUrl": "wss://cirno.example" + previous, "tokenIssuePath": "/api/token"}}
    path.write_text(json.dumps(data))
    migrate_instance(path)
    websocket = load_config(path).channels.websocket
    assert websocket["path"] == updated
    assert websocket["publicWsUrl"] == "wss://cirno.example" + updated
    assert websocket["tokenIssuePath"] == "/v0/token"
    WebSocketConfig.model_validate(websocket)


def test_cli_migrates_released_endpoint_before_constructing_new_websocket_config(released, monkeypatch):
    from cirno_server.cli.commands import app
    from typer.testing import CliRunner
    _, _, path = released
    data = read_json(path)
    data["channels"] = {"websocket": {"path": "/"}}
    path.write_text(json.dumps(data))
    launched = []
    monkeypatch.setattr("cirno_server.cli.commands.run_server", lambda config, **kwargs: launched.append(config))
    result = CliRunner().invoke(app, ["--config", str(path)])
    assert result.exit_code == 0, result.output
    assert launched[0].channels.websocket["path"] == "/v0/ws"


def test_import_reads_committed_wal_left_by_an_exited_old_process(released, released_store):
    import subprocess
    import sys
    instance, workspace, path = released
    source = released_store(instance, workspace, "a" * 32)
    database = source / "sessions.sqlite3"
    subprocess.run([sys.executable, "-c", '''import json, os, sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute("PRAGMA journal_mode=WAL")
connection.execute("UPDATE messages SET record=?", (json.dumps({"role":"user", "content":"Committed before crash"}),))
connection.commit()
os._exit(0)
''', str(database)], check=True, timeout=10)
    assert database.with_name(database.name + "-wal").exists()
    migrate_instance(path)
    manager = SessionManager(workspace, sessions_root=instance / "state/sessions")
    assert manager.get_existing("websocket:research").messages[0]["content"] == "Committed before crash"


def test_import_streams_a_large_history_instead_of_loading_its_corpus(released, released_store):
    import tracemalloc
    instance, workspace, path = released
    source = released_store(instance, workspace, "a" * 32)
    text = json.dumps({"role": "assistant", "content": "research evidence " * 64})
    with closing(sqlite3.connect(source / "sessions.sqlite3")) as db, db:
        db.executemany("INSERT INTO messages VALUES (?,?,?)", (("websocket:research", position, text) for position in range(1, 12_001)))
    tracemalloc.start()
    try:
        migrate_instance(path)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # More than 12 MB of records; importer retains a row, not two whole corpora.
    assert peak < 8 * 1024 * 1024
    with closing(sqlite3.connect(instance / "state/sessions/instance/sessions.sqlite3")) as db:
        assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 12_001


def test_active_store_marker_preserves_automation_routing_when_paths_match(released, released_store):
    instance, workspace, path = released
    released_store(instance, workspace, "a" * 32, text="Superseded workspace identity")
    released_store(instance, workspace, "b" * 32, text="Active workspace identity")
    actions = workspace / "cron/action.jsonl"
    actions.parent.mkdir()
    actions.write_text(json.dumps({"action": "add", "params": {"payload": {"session_key": "websocket:research"}}}) + "\n")
    migrate_instance(path)
    manager = SessionManager(workspace, sessions_root=instance / "state/sessions")
    assert manager.get_existing("websocket:research").messages[0]["content"] == "Active workspace identity"
    assert json.loads((instance / "state/cron/action.jsonl").read_text())["params"]["payload"]["session_key"] == "websocket:research"


def test_pending_automation_actions_follow_imported_collision_ids(released, released_store, tmp_path):
    instance, workspace, path = released
    released_store(instance, workspace, "a" * 32, text="Current")
    other = tmp_path / "older"
    released_store(instance, other, "b" * 32, text="Other")
    actions = other / "cron/action.jsonl"
    actions.parent.mkdir()
    actions.write_text(json.dumps({"action": "add", "params": {"payload": {"session_key": "websocket:research"}}}) + "\n")
    migrate_instance(path)
    renamed = read_json(instance / "state/migrations/0.1.6-to-0.2.0/report.json")["renamed"][0]["target"]
    assert json.loads((instance / "state/cron/action.jsonl").read_text())["params"]["payload"]["session_key"] == renamed


def test_released_oauth_files_are_copied_into_instance_and_shared_original_is_kept(released, tmp_path, monkeypatch):
    from oauth_cli_kit.storage import FileTokenStorage
    instance, _, path = released
    old = tmp_path / "sdk/codex.json"
    old.parent.mkdir()
    content = json.dumps({"access": "fixture", "refresh": "refresh", "expires": 2000})
    old.write_text(content)
    monkeypatch.setattr(FileTokenStorage, "get_token_path", lambda self: tmp_path / "sdk" / self._token_filename)
    migrate_instance(path)
    target = instance / "state/providers/openai_codex/codex.json"
    assert target.read_text() == content
    assert old.read_text() == content
    report = read_json(instance / "state/migrations/0.1.6-to-0.2.0/report.json")
    assert report["oauth_credentials_copied"] == ["openai_codex"]


def test_invalid_websocket_settings_stop_before_replacement_and_redact_credentials(released):
    from cirno_core.config.errors import ConfigLoadError
    _, _, path = released
    data = read_json(path)
    data["channels"] = {"websocket": {"path": "/", "token": "TOP_SECRET", "publicWsUrl": "wss://cirno.example/different"}}
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    with pytest.raises(ConfigLoadError) as error:
        migrate_instance(path)
    assert "channels.websocket" in str(error.value)
    assert "TOP_SECRET" not in str(error.value)
    assert path.read_bytes() == before
