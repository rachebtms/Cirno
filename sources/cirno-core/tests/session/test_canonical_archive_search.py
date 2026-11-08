"""Exercise the release path that summary-only history tests cannot cover."""

import shutil

import pytest

from cirno_memory.repository import MemoryRepository
from cirno_core.session.history import SessionHistoryReader
from cirno_core.session.manager import SessionManager


async def compact_and_release(manager, repo, key, boundary):
    session = await manager.state.get(key)
    await manager.state.commit_summary(session, "checkpoint", archive_end=boundary)
    await manager.state.release_archived_runtime(
        key,
        lambda messages, project: repo.archive_messages(
            messages,
            key,
            project,
            preserve_system=True,
        ),
    )


@pytest.mark.asyncio
async def test_multiple_compactions_release_restart_and_search_preserve_original_evidence(tmp_path):
    workspace = tmp_path / "workspace"
    repo = MemoryRepository(tmp_path / "home")
    manager = SessionManager(workspace)
    key = "websocket:research"
    messages = [
        {
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"测量记录 {i}: " + "background observation " * 100,
        }
        for i in range(3000)
    ]
    messages[0]["content"] = "Original calibration: threshold=0.00003125; sample=始点"
    messages[950]["content"] = "Middle calibration: threshold=0.00006250; sample=中点"
    await manager.state.import_messages(key, messages)
    try:
        for boundary in (600, 900, 1000):
            await compact_and_release(manager, repo, key, boundary)
    finally:
        await manager.state.aclose()
    reopened = SessionManager(workspace)
    try:
        access = SessionHistoryReader(reopened)
        for needle, index, canonical in [("0.00003125", 0, 0), ("0.00006250", 950, 951)]:
            found = access.search(needle, 5)
            assert [item["session_key"] for item in found] == [key]
            assert found[0]["messages"][0]["content"] == messages[index]["content"]
            assert found[0]["messages"][0]["message_index"] == canonical
        assert (
            access.read(key, query="", limit=8)["messages"][-1]["content"]
            == messages[-1]["content"].strip()
        )
    finally:
        await reopened.state.aclose()


@pytest.mark.asyncio
async def test_latest_read_stops_before_opening_released_corpus(tmp_path, monkeypatch):
    manager = SessionManager(tmp_path / "workspace")
    repo = MemoryRepository(tmp_path / "home")
    key = "websocket:latest"
    await manager.state.import_messages(
        key, [{"role": "user", "content": str(i)} for i in range(300)]
    )
    try:
        await compact_and_release(manager, repo, key, 250)

        def forbidden(_):
            raise AssertionError("A latest-message read loaded old evidence")

        monkeypatch.setattr("cirno_core.session.canonical_history.reverse_json_lines", forbidden)
        latest = SessionHistoryReader(manager).read(key, query="", limit=8)
        assert [m["content"] for m in latest["messages"]] == [str(i) for i in range(292, 300)]
    finally:
        await manager.state.aclose()


@pytest.mark.asyncio
async def test_archive_index_survives_moving_instance_and_excludes_internal_messages(tmp_path):
    original, moved = tmp_path / "original", tmp_path / "moved"
    manager = SessionManager(original / "workspace", sessions_root=original / "state" / "sessions")
    repo = MemoryRepository(original / "home")
    key = "websocket:moving"
    messages = [
        {"role": "system", "content": "private setup"},
        {"role": "user", "content": "Internal evidence", "_hidden_history": True},
        {"role": "user", "content": "Visible exact evidence"},
    ]
    try:
        await manager.state.import_messages(key, messages)
        await compact_and_release(manager, repo, key, len(messages))
    finally:
        await manager.state.aclose()
    shutil.copytree(original, moved)
    shutil.rmtree(original)
    reopened = SessionManager(moved / "workspace", sessions_root=moved / "state" / "sessions")
    try:
        read = SessionHistoryReader(reopened).read(key, query="evidence", limit=8)
        assert [(m["message_index"], m["content"]) for m in read["messages"]] == [
            (2, "Visible exact evidence")
        ]
    finally:
        await reopened.state.aclose()


@pytest.mark.asyncio
async def test_incomplete_evidence_never_releases_canonical_messages(tmp_path):
    manager = SessionManager(tmp_path / "workspace")
    repo = MemoryRepository(tmp_path / "home")
    key = "websocket:retain"
    messages = [
        {"role": "system", "content": "internal state"},
        {"role": "user", "content": "exact evidence"},
    ]
    try:
        session = await manager.state.import_messages(key, messages)
        await manager.state.commit_summary(session, "checkpoint", archive_end=2)
        with pytest.raises(ValueError, match="every released"):
            await manager.state.release_archived_runtime(
                key, lambda entries, project: repo.archive_messages(entries, key, project)
            )
        retained = await manager.state.get(key)
        assert retained.messages[:2] == messages
        assert retained.last_archived == 2
    finally:
        await manager.state.aclose()


@pytest.mark.asyncio
async def test_failed_archive_removes_partial_file_and_retains_runtime(tmp_path):
    manager = SessionManager(tmp_path / "workspace")
    repo = MemoryRepository(tmp_path / "home")
    key = "websocket:archive-failure"
    messages = [{"role": "user", "content": "irreplaceable evidence"}]
    try:
        session = await manager.state.import_messages(key, messages)
        await manager.state.commit_summary(session, "checkpoint", archive_end=1)

        def broken_archive(entries, project):
            def broken_stream():
                yield next(entries)
                raise OSError("Disk write failed")

            return repo.archive_messages(broken_stream(), key, project, preserve_system=True)

        with pytest.raises(OSError, match="Disk write failed"):
            await manager.state.release_archived_runtime(key, broken_archive)
        assert not list((repo.root / "sources").iterdir())
        retained = await manager.state.get(key)
        assert retained.messages[:1] == messages
        # A retry produces one complete searchable archive.
        await manager.state.release_archived_runtime(
            key,
            lambda entries, project: repo.archive_messages(
                entries, key, project, preserve_system=True
            ),
        )
        assert (
            SessionHistoryReader(manager).read(key, query="irreplaceable", limit=1)["messages"][0][
                "content"
            ]
            == messages[0]["content"]
        )
    finally:
        await manager.state.aclose()


@pytest.mark.parametrize("released", [False, True], ids=["current", "archived"])
async def test_search_reports_non_object_evidence_instead_of_hiding_it(tmp_path, released):
    import sqlite3

    manager = SessionManager(tmp_path / "workspace")
    key = "websocket:corrupt-evidence"
    await manager.state.import_messages(key, [{"role": "user", "content": "Irreplaceable evidence"}])
    if released:
        await compact_and_release(manager, MemoryRepository(tmp_path / "home"), key, 1)
    await manager.state.aclose()
    with sqlite3.connect(manager.sessions_dir / "sessions.sqlite3") as db:
        if released:
            relative = db.execute("SELECT path FROM runtime_archives WHERE session_key=?", (key,)).fetchone()[0]
            corrupted = manager.sessions_dir / relative
            corrupted.write_text("[]\n", encoding="utf-8")
        else:
            db.execute("UPDATE messages SET record='[]' WHERE session_key=? AND position=0", (key,))
    reopened = SessionManager(manager.workspace, sessions_root=manager.sessions_dir.parent)
    try:
        with pytest.raises(ValueError, match="record.*object"):
            SessionHistoryReader(reopened).read(key, query="", limit=10)
    finally:
        await reopened.state.aclose()
    if released:
        assert corrupted.read_text() == "[]\n"
