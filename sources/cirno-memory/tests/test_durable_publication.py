"""A committed catalog must never point at an unsynchronized memory file."""

import errno
import os
import stat

import pytest

from cirno_memory.repository import MemoryRepository


def test_failed_revision_flush_cannot_commit_metadata(tmp_path, monkeypatch):
    repo = MemoryRepository(tmp_path)
    old = repo.save(content="Original durable value", source="test fixture", scope="session", session_key="worker:a")
    original_fsync = os.fsync

    def fail_file_flush(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, "simulated flush failure")
        return original_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_file_flush)
    with pytest.raises(OSError, match="flush failure"):
        repo.save(content="Uncommitted replacement", memory_id=old["id"], expected_revision=1,
                  source="test fixture", scope="session", session_key="worker:a")
    current = repo.read(old["id"], session_key="worker:a")
    assert current["revision"] == 1
    assert current["content"] == "Original durable value"
    assert len(repo.history(old["id"], session_key="worker:a")) == 1
    assert not list(repo.root.rglob("*.tmp"))


def test_failed_evidence_flush_is_not_published_or_catalogued(tmp_path, monkeypatch):
    repo = MemoryRepository(tmp_path)
    original_fsync = os.fsync

    def fail_file_flush(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, "simulated evidence flush failure")
        return original_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_file_flush)
    with pytest.raises(OSError, match="evidence flush failure"):
        repo.archive_messages([{"role": "user", "content": "Source content"}], "worker:a")
    assert not list((repo.root / "sources").glob("*.jsonl"))
    assert not list(repo.root.rglob("*.tmp"))
    assert not repo.search(session_key="worker:a")["memories"]


def test_catalog_update_occurs_after_file_and_directory_sync(tmp_path, monkeypatch):
    import cirno_memory.atomic as atomic

    repo = MemoryRepository(tmp_path)
    old = repo.save("Original", source="fixture", scope="session", session_key="worker:a")
    events = []
    fsync = os.fsync
    publish = atomic.publish_file
    put = repo._put_record

    def record_sync(fd):
        events.append("file_sync" if stat.S_ISREG(os.fstat(fd).st_mode) else "directory_sync")
        return fsync(fd)

    def record_publish(temporary, destination):
        events.append("rename")
        return publish(temporary, destination)

    def record_put(db, record, content):
        if os.name != "nt":
            assert events[-3:] == ["file_sync", "rename", "directory_sync"]
        else:
            assert events[-2:] == ["file_sync", "rename"]
        assert (repo.home / record["path"]).read_text() == content
        return put(db, record, content)

    monkeypatch.setattr(os, "fsync", record_sync)
    monkeypatch.setattr("cirno_memory.repository.publish_file", record_publish)
    monkeypatch.setattr(repo, "_put_record", record_put)
    updated = repo.save("Replacement", source="fixture", scope="session", session_key="worker:a",
                        memory_id=old["id"], expected_revision=1)
    assert repo.read(updated["id"], session_key="worker:a")["content"] == "Replacement"


@pytest.mark.skipif(os.name == "nt", reason="Directory fsync is a POSIX facility")
def test_directory_sync_failure_keeps_prior_catalog_revision(tmp_path, monkeypatch):
    repo = MemoryRepository(tmp_path)
    old = repo.save("Original", source="fixture", scope="session", session_key="worker:a")
    original_fsync = os.fsync

    def fail_directory_sync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, "simulated directory sync failure")
        return original_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory_sync)
    with pytest.raises(OSError, match="directory sync failure"):
        repo.save("Replacement", source="fixture", scope="session", session_key="worker:a",
                  memory_id=old["id"], expected_revision=1)
    assert repo.read(old["id"], session_key="worker:a")["content"] == "Original"
    assert len(repo.history(old["id"], session_key="worker:a")) == 1
