"""Tests for the restructured MemoryStore — pure file I/O layer."""

import json
from pathlib import Path

import pytest

from cirno_core.memory.journal import HISTORY_ENTRY_MAX_CHARS
from cirno_core.memory.store import MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(tmp_path)


class TestMemoryStoreBasicIO:
    def test_read_memory_returns_empty_when_missing(self, store):
        assert store.read_memory() == ""

    def test_write_and_read_memory(self, store):
        store.write_memory("hello")
        assert store.read_memory() == "hello"

    def test_read_soul_returns_empty_when_missing(self, store):
        assert store.read_soul() == ""

    def test_write_and_read_soul(self, store):
        store.write_soul("soul content")
        assert store.read_soul() == "soul content"

    def test_read_user_returns_empty_when_missing(self, store):
        assert store.read_user() == ""

    def test_write_and_read_user(self, store):
        store.write_user("user content")
        assert store.read_user() == "user content"

    def test_get_memory_context_returns_empty_when_missing(self, store):
        assert store.get_memory_context() == ""

    def test_get_memory_context_returns_formatted_content(self, store):
        store.write_memory("important fact")
        ctx = store.get_memory_context()
        assert "Long-term Memory" in ctx
        assert "important fact" in ctx


class TestHistoryWithCursor:
    def test_append_history_returns_cursor(self, store):
        cursor = store.journal.append_history("event 1")
        assert cursor == 1
        cursor2 = store.journal.append_history("event 2")
        assert cursor2 == 2

    def test_append_history_includes_cursor_in_file(self, store):
        store.journal.append_history("event 1")
        content = store.read_file(store.journal.history_file)
        data = json.loads(content)
        assert data["cursor"] == 1

    def test_append_history_includes_session_key_when_provided(self, store):
        store.journal.append_history("event 1", session_key="telegram:chat-1")
        content = store.read_file(store.journal.history_file)
        data = json.loads(content)
        assert data["session_key"] == "telegram:chat-1"

    def test_cursor_persists_across_appends(self, store):
        store.journal.append_history("event 1")
        store.journal.append_history("event 2")
        cursor = store.journal.append_history("event 3")
        assert cursor == 3

    @pytest.mark.parametrize(
        "input_text, expected_content",
        [
            pytest.param(
                "<think>reasoning</think>final answer",
                "final answer",
                id="strips_thinking_content",
            ),
            pytest.param("<think>nothing user-facing</think>", "", id="drops_pure_leak_content"),
            pytest.param("<channel|>", "", id="drops_malformed_leak_prefix"),
        ],
    )
    def test_append_history_sanitizes_thinking(self, store, input_text, expected_content):
        cursor = store.journal.append_history(input_text)
        content = store.read_file(store.journal.history_file)
        data = json.loads(content)
        assert data["cursor"] == cursor
        assert data["content"] == expected_content

    def test_read_unprocessed_history(self, store):
        store.journal.append_history("event 1")
        store.journal.append_history("event 2")
        store.journal.append_history("event 3")
        entries = store.journal.read_unprocessed_history(since_cursor=1)
        assert len(entries) == 2
        assert entries[0]["cursor"] == 2

    def test_read_unprocessed_history_returns_all_when_cursor_zero(self, store):
        store.journal.append_history("event 1")
        store.journal.append_history("event 2")
        entries = store.journal.read_unprocessed_history(since_cursor=0)
        assert len(entries) == 2


    def test_append_history_allocates_unique_cursors_under_concurrent_writes(self, store):
        """Regression: concurrent appends must not allocate duplicate cursors."""
        import threading

        writers = 16
        start = threading.Barrier(writers)
        cursors: list[int] = []
        lock = threading.Lock()

        def worker(i):
            start.wait()
            c = store.journal.append_history(f"event {i}")
            with lock:
                cursors.append(c)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(writers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(cursors) == writers
        assert len(set(cursors)) == writers, f"duplicate cursors: {sorted(cursors)}"
        assert sorted(cursors) == list(range(1, writers + 1))
        persisted = store.journal.read_unprocessed_history(since_cursor=0)
        assert sorted(e["cursor"] for e in persisted) == list(range(1, writers + 1))

    def test_compact_history_drops_oldest(self, tmp_path):
        store = MemoryStore(tmp_path, max_history_entries=2)
        store.journal.append_history("event 1")
        store.journal.append_history("event 2")
        store.journal.append_history("event 3")
        store.journal.append_history("event 4")
        store.journal.append_history("event 5")
        store.journal.set_last_dream_cursor(5)
        store.journal.compact_history()
        entries = store.journal.read_unprocessed_history(since_cursor=0)
        assert len(entries) == 2
        assert entries[0]["cursor"] in {4, 5}

    def test_compact_history_preserves_entries_after_dream_cursor(self, tmp_path):
        store = MemoryStore(tmp_path, max_history_entries=50)
        for index in range(1, 101):
            store.journal.append_history(f"event {index}")
        store.journal.set_last_dream_cursor(20)

        store.journal.compact_history()

        entries = store.journal.read_unprocessed_history(since_cursor=0)
        assert [entry["cursor"] for entry in entries] == list(range(21, 101))


class TestAppendHistoryHardCap:
    """Journal summaries have a bounded size and report truncation once."""

    def test_oversized_entry_is_truncated(self, store):
        """An entry above HISTORY_ENTRY_MAX_CHARS is truncated before being persisted."""
        huge = "x" * (HISTORY_ENTRY_MAX_CHARS + 10_000)
        store.journal.append_history(huge)
        entry = store.journal.read_unprocessed_history(since_cursor=0)[0]
        assert len(entry["content"]) <= HISTORY_ENTRY_MAX_CHARS + 50

    def test_oversize_warning_is_emitted_once(self, store, monkeypatch):
        """Repeated oversized writes should warn only on the first occurrence."""
        records: list[str] = []
        monkeypatch.setattr(
            "cirno_core.memory.journal.logger.warning",
            lambda message, *args: records.append(message.format(*args)),
        )
        huge = "x" * (HISTORY_ENTRY_MAX_CHARS + 1)
        store.journal.append_history(huge)
        store.journal.append_history(huge)
        store.journal.append_history(huge)

        oversize_warnings = [r for r in records if "exceeds" in r and "chars" in r]
        assert len(oversize_warnings) == 1

    def test_custom_max_chars_overrides_default(self, store):
        """Callers that pass max_chars should get their tighter cap applied."""
        store.journal.append_history("a" * 500, max_chars=100)
        entry = store.journal.read_unprocessed_history(since_cursor=0)[0]
        assert len(entry["content"]) <= 150  # 100 + "\n... (truncated)"

    def test_normal_sized_entries_unaffected(self, store):
        """The hard cap must not alter entries that fit within it."""
        msg = "normal short entry"
        store.journal.append_history(msg)
        entry = store.journal.read_unprocessed_history(since_cursor=0)[0]
        assert entry["content"] == msg


class TestDreamCursor:
    def test_initial_cursor_is_zero(self, store):
        assert store.journal.get_last_dream_cursor() == 0

    def test_returns_zero_when_empty(self, store):
        assert store.journal.get_latest_cursor() == 0

    def test_returns_cursor_of_last_entry(self, store):
        store.journal.append_history("event 1")
        store.journal.append_history("event 2")
        store.journal.append_history("event 3")

        assert store.journal.get_latest_cursor() == 3

    def test_returns_zero_when_no_entries(self, store):
        store.journal.history_file.write_text("", encoding="utf-8")

        assert store.journal.get_latest_cursor() == 0

    def test_matches_next_cursor_minus_one(self, store):
        store.journal.append_history("event 1")
        store.journal.append_history("event 2")

        assert store.journal.get_latest_cursor() == max(store.journal._next_cursor() - 1, 0)

    def test_set_and_get_cursor(self, store):
        store.journal.set_last_dream_cursor(5)
        assert store.journal.get_last_dream_cursor() == 5

    def test_cursor_persists(self, store):
        store.journal.set_last_dream_cursor(3)
        store2 = MemoryStore(store.workspace)
        assert store2.journal.get_last_dream_cursor() == 3

    def test_git_restore_rolls_back_dream_cursor(self, tmp_path):
        store = MemoryStore(tmp_path)
        store.write_memory("before")
        store.journal.set_last_dream_cursor(1)
        assert store.git.init() is True

        store.write_memory("after")
        store.journal.set_last_dream_cursor(2)
        dream_sha = store.git.auto_commit("dream: update")
        assert dream_sha is not None

        store.write_memory("newer")
        store.journal.set_last_dream_cursor(3)

        restore_sha = store.git.revert(dream_sha)

        assert restore_sha is not None
        assert store.read_memory() == "before"
        assert store.journal.get_last_dream_cursor() == 1


def test_raw_archive_handles_none_timestamp_and_missing_role(tmp_path: Path) -> None:
    """raw_archive and _format_messages must safely format messages with None timestamp or missing role.

    Prevents TypeError on NoneType[:16] slicing and KeyError on missing 'role'
    when raw-dumping unconsolidated history entries without timestamps or role fields.
    """
    memory = MemoryStore(tmp_path)
    messages = [
        {"content": "message with none timestamp", "timestamp": None, "role": "user"},
        {"content": "message with int timestamp", "timestamp": 1720000000, "role": "assistant"},
        {"content": "message with missing role", "timestamp": "2026-07-28T12:00:00"},
    ]
    memory.raw_archive(messages, session_key="cli:test")
    raw_history = memory.journal.history_file.read_text(encoding="utf-8")
    assert "[?] USER: message with none timestamp" in raw_history
    assert "[1720000000] ASSISTANT: message with int timestamp" in raw_history
    assert "[2026-07-28T12:00] UNKNOWN: message with missing role" in raw_history


@pytest.mark.parametrize("content", ["x" * 20000, "科研记录🧊" * 4000])
def test_large_history_tail_does_not_rescan_the_growing_journal(store, monkeypatch, content):
    store.journal.append_history("Earlier evidence")
    assert store.journal.append_history(content) == 2
    assert store.journal._read_last_entry()["content"] == content
    with store.journal.history_file.open("a") as stream:
        stream.write("\n \n")

    def no_full_scan():
        pytest.fail("A valid large final record must not trigger a complete journal scan")
        yield

    monkeypatch.setattr(store.journal, "iter_valid_entries", no_full_scan)
    assert store.journal.append_history("Next checkpoint") == 3
