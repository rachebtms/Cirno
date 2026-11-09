"""Concurrent memory tools and settings share one profile index writer."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from cirno_memory.repository import MemoryRepository


def test_concurrent_profile_sync_is_idempotent(tmp_path, monkeypatch):
    (tmp_path / "SOUL.md").write_text("Shared assistant identity", encoding="utf-8")
    first, second = MemoryRepository(tmp_path), MemoryRepository(tmp_path)
    entered, release, second_saving = Event(), Event(), Event()
    save_first, save_second = first.save, second.save

    def delayed_save(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return save_first(*args, **kwargs)

    def observed_save(*args, **kwargs):
        second_saving.set()
        return save_second(*args, **kwargs)

    monkeypatch.setattr(first, "save", delayed_save)
    monkeypatch.setattr(second, "save", observed_save)
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(first.sync_profiles)
        try:
            assert entered.wait(3)
            two = pool.submit(second.sync_profiles)
            # Without serialization, both writers have read the absent revision
            # before either save is allowed to complete.
            second_saving.wait(.2)
        finally:
            release.set()
        one.result(timeout=3)
        two.result(timeout=3)
    rows = first.search("identity", layer="profile", maintenance=True)["memories"]
    assert len(rows) == 1
    assert rows[0]["revision"] == 1
    assert first.read(rows[0]["id"], maintenance=True)["content"] == "Shared assistant identity"
