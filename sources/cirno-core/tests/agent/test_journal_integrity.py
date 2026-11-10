"""Journal reads and retention must never erase corrupt evidence silently."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from cirno_core.memory.journal import MemoryJournal


@pytest.mark.parametrize(
    "record",
    [
        "not-json",
        "[]",
        json.dumps({"cursor": True, "timestamp": "2026-11-08", "content": "observation"}),
        json.dumps({"cursor": 2, "timestamp": "2026-11-08"}),
    ],
)
@pytest.mark.parametrize("operation", ["read", "compact", "append"])
def test_corruption_is_reported_without_rewriting_the_journal(tmp_path, record, operation):
    journal = MemoryJournal(tmp_path, max_history_entries=1)
    valid = lambda cursor: json.dumps(
        {"cursor": cursor, "timestamp": "2026-11-08", "content": "valid"}
    )
    # A bad tail must also prevent allocation of a new cursor.
    original = (valid(1) + "\n" + valid(2) + "\n" + record + "\n").encode()
    journal.history_file.write_bytes(original)
    journal.set_last_dream_cursor(2)

    with pytest.raises(ValueError, match="history.jsonl"):
        if operation == "read":
            journal.read_unprocessed_history(0)
        elif operation == "compact":
            journal.compact_history()
        else:
            journal.append_history("Do not append after an invalid tail.")

    assert journal.history_file.read_bytes() == original


def test_independent_journals_allocate_distinct_cursors(tmp_path, monkeypatch):
    journals = [MemoryJournal(tmp_path), MemoryJournal(tmp_path)]
    original_next_cursor = MemoryJournal._next_cursor
    start = threading.Barrier(2)

    def slow_allocation(self):
        cursor = original_next_cursor(self)
        time.sleep(0.03)
        return cursor

    monkeypatch.setattr(MemoryJournal, "_next_cursor", slow_allocation)

    def append(index):
        start.wait(timeout=3)
        return journals[index].append_history(f"measurement-{index}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        cursors = list(pool.map(append, range(2)))

    assert sorted(cursors) == [1, 2]
    entries = journals[0].read_unprocessed_history(0)
    assert [entry["cursor"] for entry in entries] == [1, 2]
    assert {entry["content"] for entry in entries} == {"measurement-0", "measurement-1"}


@pytest.mark.parametrize(("counter", "expected"), [(2, 11), (100, 101)])
def test_cursor_allocation_preserves_ahead_counter_and_newer_tail(tmp_path, counter, expected):
    journal = MemoryJournal(tmp_path)
    journal.history_file.write_text(
        json.dumps(
            {
                "cursor": 10,
                "timestamp": "2026-11-08",
                "content": "retained evidence",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    journal._cursor_file.write_text(str(counter), encoding="utf-8")

    assert journal.append_history("new observation") == expected
    assert journal.read_unprocessed_history(0)[-1]["cursor"] == expected


@pytest.mark.parametrize("filename", [".cursor", ".dream_cursor"])
@pytest.mark.parametrize("content", ["not-a-number", "-1"])
def test_invalid_counter_blocks_its_operation_without_modifying_files(tmp_path, filename, content):
    journal = MemoryJournal(tmp_path)
    counter = journal.memory_dir / filename
    counter.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="memory cursor"):
        if filename == ".cursor":
            journal.append_history("Do not allocate from a corrupt counter.")
        else:
            journal.compact_history()

    assert counter.read_text(encoding="utf-8") == content
    assert not journal.history_file.exists()


def test_initial_memory_version_contains_a_valid_dream_cursor(tmp_path):
    from cirno_core.memory.store import MemoryStore

    memory = MemoryStore(tmp_path)
    assert memory.git.init()
    assert memory.journal._dream_cursor_file.read_text(encoding="utf-8") == "0"
    assert memory.journal.get_last_dream_cursor() == 0


def test_failed_retention_replacement_preserves_evidence_and_removes_staging(tmp_path, monkeypatch):
    journal = MemoryJournal(tmp_path, max_history_entries=1)
    journal.append_history("first observation")
    journal.append_history("second observation")
    journal.set_last_dream_cursor(2)
    original = journal.history_file.read_bytes()
    files_before = set(journal.memory_dir.iterdir())

    def fail_replace(_source, target):
        assert target == journal.history_file
        raise OSError("retention replacement failed")

    monkeypatch.setattr("cirno_core.utils.atomic_file.replace_atomic", fail_replace)
    with pytest.raises(OSError, match="retention replacement failed"):
        journal.compact_history()

    assert journal.history_file.read_bytes() == original
    assert set(journal.memory_dir.iterdir()) == files_before
def test_consolidation_journal_retention_keeps_indexed_evidence_and_does_not_need_dream(tmp_path):
    from cirno_core.memory.journal import MemoryJournal
    from cirno_memory.repository import MemoryRepository
    journal = MemoryJournal(tmp_path, max_history_entries=2)
    for i in range(5):
        journal.append_history(f"Exact event {i}", session_key="worker:a", archive_id=f"batch-{i}")
    assert [entry["cursor"] for entry, _ in journal.iter_valid_entries()] == [4, 5]
    assert journal.get_last_dream_cursor() == 0
    repo = MemoryRepository(tmp_path)
    assert repo.read_source("history-1", session_key="worker:a")["content"] == "Exact event 0"
    assert journal.append_history("Exact event 4", session_key="worker:a", archive_id="batch-4") == 5
    assert journal.append_history("Next event", session_key="worker:a", archive_id="batch-5") == 6


def test_retention_waits_for_failed_catalog_ingestion_and_retry_does_not_duplicate(tmp_path, monkeypatch):
    from cirno_core.memory.journal import MemoryJournal
    from cirno_memory.repository import MemoryRepository
    journal = MemoryJournal(tmp_path, max_history_entries=2)
    ingest = MemoryRepository.ingest_history
    def fail(*args, **kwargs):
        raise OSError("index storage unavailable")
    monkeypatch.setattr(MemoryRepository, "ingest_history", fail)
    with pytest.raises(OSError, match="storage unavailable"):
        journal.append_history("Original evidence", session_key="worker:a", archive_id="first")
    monkeypatch.setattr(MemoryRepository, "ingest_history", ingest)
    for i in range(4):
        journal.append_history(f"Later {i}", session_key="worker:a", archive_id=f"later-{i}")
    assert len(list(journal.iter_valid_entries())) == 5
    assert journal.append_history("Original evidence", session_key="worker:a", archive_id="first") == 1
    assert [entry["cursor"] for entry, _ in journal.iter_valid_entries()] == [4, 5]
    assert MemoryRepository(tmp_path).read_source("history-1", session_key="worker:a")["content"] == "Original evidence"
