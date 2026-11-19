"""Type-changing and SQLite restoration retain old targets on failed publication."""

import shutil
import sqlite3
from pathlib import Path

import pytest
from cirno_server.backup.archive import Backups


def restore(tmp_path, kind):
    root, extra = tmp_path / "instance", tmp_path / "extra"
    root.mkdir()
    root.joinpath("config.json").write_text("{}")
    if kind == "directory":
        extra.mkdir()
        extra.joinpath("paper.txt").write_text("Backup directory")
    elif kind == "sqlite":
        with sqlite3.connect(extra) as db:
            db.execute("CREATE TABLE research (value)")
            db.execute("INSERT INTO research VALUES ('Backup database')")
    else:
        extra.write_text("Backup file")
    backup = Backups(root / "config.json")
    exported, _ = backup.create([str(extra)])
    upload = tmp_path / "upload.tar.gz"
    shutil.copy2(exported, upload)
    preview = backup.inspect(upload)
    backup.prepare_restore(preview["id"], {"extras/0": str(extra)})
    return backup, extra, backup._stage(preview["id"]) / "extras" / "0"


def test_failed_directory_copy_retains_the_file_it_would_replace(tmp_path, monkeypatch):
    backup, extra, staged = restore(tmp_path, "directory")
    shutil.rmtree(extra)
    extra.write_text("Current file")
    copy = shutil.copy2

    def failed(source, target, **kwargs):
        if source == staged / "paper.txt":
            raise OSError("Fixture directory copy failed")
        return copy(source, target, **kwargs)

    monkeypatch.setattr("cirno_server.backup.archive.shutil.copy2", failed)
    with pytest.raises(OSError, match="Fixture directory copy failed"):
        backup.apply_pending()
    assert extra.is_file() and extra.read_text() == "Current file"


@pytest.mark.parametrize("kind", ["file", "sqlite"])
def test_failed_file_publication_retains_old_directory_or_database_sidecars(tmp_path, monkeypatch, kind):
    backup, extra, _ = restore(tmp_path, kind)
    if kind == "file":
        extra.unlink()
        extra.mkdir()
        extra.joinpath("paper.txt").write_text("Current directory")
    else:
        extra.with_name(extra.name + "-wal").write_bytes(b"Current WAL")
        extra.with_name(extra.name + "-shm").write_bytes(b"Current SHM")
        before = extra.read_bytes()
    replace = Path.replace

    def failed(source, target):
        if source.name.startswith(".cirno-restore-") and target == extra:
            raise OSError("Fixture publication failed")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", failed)
    with pytest.raises(OSError, match="Fixture publication failed"):
        backup.apply_pending()
    if kind == "file":
        assert extra.joinpath("paper.txt").read_text() == "Current directory"
    else:
        assert extra.read_bytes() == before
        assert extra.with_name(extra.name + "-wal").read_bytes() == b"Current WAL"
        assert extra.with_name(extra.name + "-shm").read_bytes() == b"Current SHM"


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_valid_restore_still_supports_changing_between_a_file_and_directory(tmp_path, kind):
    backup, extra, _ = restore(tmp_path, kind)
    if kind == "file":
        extra.unlink()
        extra.mkdir()
        extra.joinpath("paper.txt").write_text("Current directory")
    else:
        shutil.rmtree(extra)
        extra.write_text("Current file")
    assert backup.apply_pending()
    assert (extra.read_text() if kind == "file" else extra.joinpath("paper.txt").read_text()) == (
        "Backup file" if kind == "file" else "Backup directory"
    )


@pytest.mark.parametrize("failure", ["second-sidecar", "after-publication"])
def test_sqlite_sidecars_follow_the_actual_publication_outcome(tmp_path, monkeypatch, failure):
    backup, extra, _ = restore(tmp_path, "sqlite")
    wal, shm = [extra.with_name(extra.name + suffix) for suffix in ("-wal", "-shm")]
    wal.write_bytes(b"Current WAL")
    shm.write_bytes(b"Current SHM")
    before = extra.read_bytes()
    replace = Path.replace

    def interrupted(source, target):
        if failure == "second-sidecar" and source == shm:
            raise OSError("Fixture sidecar move failed")
        result = replace(source, target)
        if failure == "after-publication" and source.name.startswith(".cirno-restore-") and target == extra:
            raise OSError("Fixture interruption after publication")
        return result

    monkeypatch.setattr(Path, "replace", interrupted)
    with pytest.raises(OSError, match="Fixture"):
        backup.apply_pending()
    if failure == "second-sidecar":
        assert extra.read_bytes() == before
        assert wal.read_bytes() == b"Current WAL" and shm.read_bytes() == b"Current SHM"
        assert not list(extra.parent.glob(".cirno-original-*.tmp"))
    else:
        assert not wal.exists() and not shm.exists()
        originals = list(extra.parent.glob(".cirno-original-*.tmp"))
        assert {path.read_bytes() for path in originals} == {b"Current WAL", b"Current SHM"}
        with sqlite3.connect(extra) as db:
            assert db.execute("SELECT value FROM research").fetchone() == ("Backup database",)


def test_failed_type_conflict_rollback_reports_where_original_data_remains(tmp_path, monkeypatch):
    backup, extra, _ = restore(tmp_path, "file")
    extra.unlink()
    extra.mkdir()
    extra.joinpath("paper.txt").write_text("Current directory")
    replace = Path.replace

    def denied(source, target):
        if target == extra:
            raise OSError("Fixture publication and rollback unavailable")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", denied)
    with pytest.raises(OSError, match="prior data remains at"):
        backup.apply_pending()
    originals = list(extra.parent.glob(".cirno-original-*.tmp"))
    assert len(originals) == 1 and originals[0].joinpath("paper.txt").read_text() == "Current directory"
