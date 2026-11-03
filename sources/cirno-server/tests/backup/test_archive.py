"""Round-trip the complete instance, including WAL data and external credentials."""

import io
import shutil
import sqlite3
import tarfile

import pytest
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_server.backup.archive import Backups


@pytest.fixture
def backup(tmp_path):
    root = tmp_path / "instance"
    root.mkdir()
    save_config(Config(), root / "config.json")
    for name, text in {
        "home/SOUL.md": "personality",
        "home/memory/MEMORY.md": "research",
        "home/skills/physics/SKILL.md": "skill",
        "workspace/result.md": "result",
        "state/context.json": "saved reasoning",
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return Backups(root / "config.json")


def test_round_trip_complete_instance_with_wal_and_external_credentials(backup, tmp_path):
    login = tmp_path / "tea"
    login.mkdir()
    (login / "config.yml").write_text("login: test-owner")
    db = backup.root / "state" / "sessions.sqlite3"
    with sqlite3.connect(db) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE messages (text)")
        writer.execute("INSERT INTO messages VALUES (?)", ("preserved conversation",))
        writer.commit()
        archive, manifest = backup.create([str(login)])
    with tarfile.open(archive) as tar:
        assert "instance/home/SOUL.md" in tar.getnames()
        assert not any(name.endswith("-wal") for name in tar.getnames())
        assert not any("/exports/" in name or "/staging/" in name for name in tar.getnames())
    uploaded = tmp_path / "upload.gz"
    shutil.copy2(archive, uploaded)
    preview = backup.inspect(uploaded)
    assert not uploaded.exists()
    (backup.root / "home" / "SOUL.md").write_text("changed")
    (backup.root / "state" / "unrelated.json").write_text("remove stale state")
    (login / "config.yml").write_text("changed login")
    (login / "keep.txt").write_text("unrelated extra file")
    backup.prepare_restore(preview["id"], {"extras/0": str(login)})
    assert backup.apply_pending()
    assert (backup.root / "home" / "SOUL.md").read_text() == "personality"
    assert not (backup.root / "state" / "unrelated.json").exists()
    assert (login / "config.yml").read_text() == "login: test-owner"
    assert (login / "keep.txt").read_text() == "unrelated extra file"
    with sqlite3.connect(db) as reader:
        assert reader.execute("SELECT text FROM messages").fetchone()[0] == "preserved conversation"
    assert not backup.apply_pending()


@pytest.mark.parametrize(
    "malicious", ["../escape", "/absolute", "instance/state/backups/restore-plan.json"]
)
def test_invalid_archive_cannot_write_outside_staging(backup, tmp_path, malicious):
    archive, _ = backup.create([])
    with tarfile.open(archive, "r:gz") as old:
        files = [
            (member, old.extractfile(member).read() if member.isfile() else None) for member in old
        ]
    bad = tmp_path / "bad.tar.gz"
    with tarfile.open(bad, "w:gz") as tar:
        for member, content in files:
            tar.addfile(member, io.BytesIO(content) if content is not None else None)
        member = tarfile.TarInfo(malicious)
        member.size = 4
        tar.addfile(member, io.BytesIO(b"evil"))
    with pytest.raises(ValueError):
        backup.inspect(bad)
    assert not (tmp_path / "escape").exists()
    assert not list((backup.store / "staging").iterdir())


def test_symlinks_round_trip_without_extracting_through_links(backup, tmp_path):
    (backup.root / "workspace" / "shortcut").symlink_to("result.md")
    archive, _ = backup.create([])
    uploaded = tmp_path / "copy.gz"
    shutil.copy2(archive, uploaded)
    preview = backup.inspect(uploaded)
    backup.prepare_restore(preview["id"], {})
    backup.apply_pending()
    assert (backup.root / "workspace" / "shortcut").is_symlink()
    assert (backup.root / "workspace" / "shortcut").read_text() == "result"


def test_recommendations_discover_cli_credentials_and_old_workspaces(backup, tmp_path, monkeypatch):
    from types import SimpleNamespace

    tea = tmp_path / "tea-login"
    tea.mkdir()
    old = tmp_path / "old-project"
    old.mkdir()
    monkeypatch.setenv("TEA_CONFIG_DIR", str(tea))
    sessions = SimpleNamespace(
        list_session_metadata=lambda: [
            {"metadata": {"workspace_scope": {"project_path": str(old)}}}
        ]
    )
    catalog = backup.recommendations(sessions)
    assert any(
        item["path"] == str(tea) and item["kind"] == "tools" for item in catalog["recommended"]
    )
    assert any(
        item["path"] == str(old) and item["kind"] == "workspace" for item in catalog["recommended"]
    )


def test_failed_instance_copy_restores_original_data(backup, tmp_path, monkeypatch):
    from cirno_server.backup import archive as module

    archive, _ = backup.create([])
    uploaded = tmp_path / "copy.gz"
    shutil.copy2(archive, uploaded)
    preview = backup.inspect(uploaded)
    (backup.root / "home" / "SOUL.md").write_text("current owner data")
    backup.prepare_restore(preview["id"], {})
    merge = module._merge

    def fail(source, target):
        if source == backup.store / "staging" / preview["id"] / "instance":
            raise OSError("disk full")
        return merge(source, target)

    monkeypatch.setattr(module, "_merge", fail)
    with pytest.raises(OSError, match="disk full"):
        backup.apply_pending()
    assert (backup.root / "home" / "SOUL.md").read_text() == "current owner data"
    assert (backup.store / "restore-plan.json").exists()


def test_archive_restores_account_and_existing_browser_session(backup, tmp_path):
    from cirno_server.webui.auth.store import AccountStore

    store = AccountStore(backup.root / "state" / "webui-auth.sqlite3")
    token = store.register("owner", "LongPassword!123")
    archive, _ = backup.create([])
    uploaded = tmp_path / "auth.gz"
    shutil.copy2(archive, uploaded)
    preview = backup.inspect(uploaded)
    store.logout(token)
    backup.prepare_restore(preview["id"], {})
    backup.apply_pending()
    restored = AccountStore(store.path)
    assert restored.authenticated(token)


def test_external_sqlite_snapshot_excludes_wal_and_replaces_stale_sidecars(backup, tmp_path):
    external = tmp_path / "tool-data"
    external.mkdir()
    database = external / "login.sqlite3"
    with sqlite3.connect(database) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE login (owner)")
        writer.execute("INSERT INTO login VALUES ('owner')")
        writer.commit()
        archive, _ = backup.create([str(external)])
    with tarfile.open(archive) as tar:
        assert "extras/0/login.sqlite3-wal" not in tar.getnames()
    uploaded = tmp_path / "copy.gz"
    shutil.copy2(archive, uploaded)
    preview = backup.inspect(uploaded)
    database.with_name("login.sqlite3-wal").write_bytes(b"stale")
    database.with_name("login.sqlite3-shm").write_bytes(b"stale")
    backup.prepare_restore(preview["id"], {"extras/0": str(external)})
    backup.apply_pending()
    assert not database.with_name("login.sqlite3-wal").exists()
    assert not database.with_name("login.sqlite3-shm").exists()
    with sqlite3.connect(database) as reader:
        assert reader.execute("SELECT owner FROM login").fetchone()[0] == "owner"
