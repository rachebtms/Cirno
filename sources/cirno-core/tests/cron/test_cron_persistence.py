"""Persistence tests for ``cirno_core.cron.service.CronService``.

These tests target the specific failure mode where a corrupt or partially
written ``jobs.json`` would silently turn into an empty job list on the next
start, deleting every scheduled job.  See ``fix(cron): atomic write for
jobs.json + don't silently overwrite corrupt store``.
"""

from __future__ import annotations

import errno
import json
from pathlib import Path
from typing import Callable

import pytest

from cirno_core.cron.repository import load_jobs
from cirno_core.cron.service import CronService
from cirno_core.cron.types import CronJob, CronPayload, CronSchedule


def _seeded_store(tmp_path: Path) -> tuple[CronService, Path]:
    """Build a service with one persisted job on disk and return both the
    service and the resolved store path.  Adds the job via the action log
    (the path used when the service is not running) and then triggers a
    merge so ``jobs.json`` is written, mirroring the persisted on-disk
    state seen in production."""
    store_path = tmp_path / "cron" / "jobs.json"
    service = CronService(store_path)
    service.add_job(
        name="Daily Loving Message",
        schedule=CronSchedule(kind="cron", expr="0 10 * * *", tz="Asia/Kuwait"),
        message="hello",
    )
    # add_job appended to action.jsonl; flush to jobs.json by toggling
    # ``_running`` long enough for ``_merge_action`` to do its rewrite.
    service._running = True
    try:
        service._load_store()
    finally:
        service._running = False
    assert store_path.exists()
    return service, store_path


def _corrupt_store(tmp_path: Path) -> Path:
    store_path = tmp_path / "cron" / "jobs.json"
    store_path.parent.mkdir(parents=True)
    store_path.write_text("{not valid json", encoding="utf-8")
    return store_path


def _assert_original_unchanged(store_path: Path) -> None:
    assert store_path.read_text(encoding="utf-8") == "{not valid json"
    assert not list(store_path.parent.glob("jobs.json.corrupt-*"))


def _system_job(job_id: str = "dream") -> CronJob:
    return CronJob(
        id=job_id,
        name="Dream",
        schedule=CronSchedule(kind="cron", expr="0 */2 * * *", tz="UTC"),
        payload=CronPayload(kind="system_event"),
    )


def test_save_store_is_atomic(tmp_path: Path) -> None:
    """``_save_store`` must use temp-file + rename so an interrupted write
    cannot leave the destination truncated or invalid."""
    service, store_path = _seeded_store(tmp_path)

    # Simulate an arbitrary save and confirm the result parses cleanly and
    # no orphan ``.tmp`` is left behind.
    service._save_store()
    data = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(data["jobs"]) == 1

    tmp_files = list(store_path.parent.glob("*.tmp"))
    assert tmp_files == [], f"unexpected temp files left behind: {tmp_files}"


def test_save_store_failure_does_not_corrupt_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If writing the temp file blows up partway through, the previous
    ``jobs.json`` must remain readable.  This is the regression we are
    actually fixing: pre-fix, ``write_text`` would truncate the destination
    in place and leave it corrupt."""
    service, store_path = _seeded_store(tmp_path)
    original = store_path.read_bytes()

    # Inject a failure inside the temp-file write.  ``os.replace`` should
    # never run; the destination must keep its previous content.
    real_open = open

    def boom(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if str(path).endswith(".tmp"):
            raise OSError("simulated disk full")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", boom)

    with pytest.raises(OSError, match="simulated disk full"):
        service._save_store()

    assert store_path.read_bytes() == original


@pytest.mark.parametrize("operation", ["add", "update", "delete"])
def test_action_log_survives_failed_store_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    writer, store_path = _seeded_store(tmp_path)
    job = writer.list_jobs(include_disabled=True)[0]
    if operation == "add":
        writer.add_job(
            name="New reminder",
            schedule=CronSchedule(kind="every", every_ms=60_000),
            message="hello",
            session_key="cli:test",
            origin_channel="cli",
            origin_chat_id="test",
        )
    elif operation == "update":
        writer.update_job(job.id, name="Updated reminder")
    else:
        assert writer.remove_job(job.id) == "removed"
    expected = [(j.id, j.name) for j in writer.list_jobs(include_disabled=True)]
    action_path = store_path.parent / "action.jsonl"
    pending_actions = action_path.read_bytes()
    original_store = store_path.read_bytes()
    assert pending_actions

    gateway = CronService(store_path)
    gateway._running = True

    def fail_write(path: Path, content: str) -> None:
        raise OSError(errno.ENOSPC, "simulated disk full")

    monkeypatch.setattr(gateway, "_atomic_write", fail_write)
    with pytest.raises(OSError, match="simulated disk full"):
        gateway._load_store()

    assert store_path.read_bytes() == original_store
    assert action_path.read_bytes() == pending_actions

    # Recover from disk, without relying on the failed gateway's dirty snapshot.
    restarted = CronService(store_path)
    restarted._running = True
    assert [(j.id, j.name) for j in restarted.list_jobs(include_disabled=True)] == expected
    assert action_path.read_bytes() == b""
    assert [(j.id, j.name) for j in CronService(store_path).list_jobs(include_disabled=True)] == expected


def test_saved_actions_can_be_replayed_if_log_cleanup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer, store_path = _seeded_store(tmp_path)
    job = writer.add_job(
        name="New reminder",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        message="hello",
        session_key="cli:test",
        origin_channel="cli",
        origin_chat_id="test",
    )
    action_path = store_path.parent / "action.jsonl"
    pending_actions = action_path.read_bytes()
    real_write_text = Path.write_text

    def fail_cleanup(path: Path, *args, **kwargs):
        if path == action_path:
            raise OSError("simulated action log cleanup failure")
        return real_write_text(path, *args, **kwargs)

    gateway = CronService(store_path)
    gateway._running = True
    with monkeypatch.context() as patch:
        patch.setattr(Path, "write_text", fail_cleanup)
        with pytest.raises(OSError, match="simulated action log cleanup failure"):
            gateway._load_store()

    saved_ids = [entry["id"] for entry in json.loads(store_path.read_text())["jobs"]]
    assert saved_ids.count(job.id) == 1
    assert action_path.read_bytes() == pending_actions

    restarted = CronService(store_path)
    restarted._running = True
    assert {j.id for j in restarted.list_jobs(include_disabled=True)} == set(saved_ids)
    assert action_path.read_bytes() == b""
    persisted = CronService(store_path).list_jobs(include_disabled=True)
    assert len(persisted) == len(saved_ids)
    assert {j.id for j in persisted} == set(saved_ids)


def test_atomic_write_ignores_unsupported_directory_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """vboxsf-like filesystems can open directories but reject directory fsync."""
    store_path = tmp_path / "cron" / "jobs.json"
    dir_fd = 987654

    def fake_open(path: str, flags: int) -> int:
        # Windows I/O uses an extended path to this same directory.
        assert Path(path).samefile(store_path.parent)
        return dir_fd

    def fake_fsync(fd: int) -> None:
        if fd == dir_fd:
            raise OSError(errno.EINVAL, "Invalid argument")

    def fake_close(fd: int) -> None:
        assert fd == dir_fd

    with monkeypatch.context() as patch:
        patch.setattr("os.open", fake_open)
        patch.setattr("os.fsync", fake_fsync)
        patch.setattr("os.close", fake_close)

        CronService._atomic_write(store_path, '{"version": 1, "jobs": []}')

    assert store_path.read_text(encoding="utf-8") == '{"version": 1, "jobs": []}'
    assert list(store_path.parent.glob("*.tmp")) == []


def test_repeated_reads_of_corrupt_store_preserve_original(tmp_path):
    store_path = _corrupt_store(tmp_path)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="corrupt.*restore jobs.json"):
            load_jobs(store_path)
        _assert_original_unchanged(store_path)


def test_start_refuses_to_overwrite_corrupt_store(tmp_path: Path) -> None:
    """``start`` must abort instead of running ``_save_store`` against an
    empty in-memory state when the on-disk store is corrupt.  Otherwise the
    next save would overwrite the (recoverable) corrupt file with an empty
    job list and the user's jobs would be unrecoverable."""
    store_path = tmp_path / "cron" / "jobs.json"
    store_path.parent.mkdir(parents=True)
    store_path.write_text("{still not json", encoding="utf-8")

    service = CronService(store_path)
    import asyncio

    with pytest.raises(RuntimeError, match="corrupt"):
        asyncio.run(service.start())

    # Service is left in a stopped state so the operator notices.
    assert service._running is False

    assert store_path.read_text() == "{still not json"
    assert not list(store_path.parent.glob("jobs.json.corrupt-*"))


def test_reload_reports_corruption_without_overwriting_file_or_memory(tmp_path):
    service, store_path = _seeded_store(tmp_path)
    snapshot = service._load_store()
    store_path.write_text("{not valid json")
    with pytest.raises(RuntimeError, match="corrupt.*restore jobs.json"):
        service.list_jobs(include_disabled=True)
    assert service._store is snapshot
    _assert_original_unchanged(store_path)


@pytest.mark.parametrize(
    ("api_name", "call"),
    [
        ("list_jobs", lambda service: service.list_jobs()),
        ("get_job", lambda service: service.get_job("missing")),
        ("status", lambda service: service.status()),
        ("remove_job", lambda service: service.remove_job("missing")),
        ("enable_job", lambda service: service.enable_job("missing", enabled=False)),
        ("update_job", lambda service: service.update_job("missing", name="new name")),
        ("register_system_job", lambda service: service.register_system_job(_system_job())),
        ("remove_system_job", lambda service: service.remove_system_job("heartbeat")),
    ],
)
def test_public_apis_raise_clear_error_for_unavailable_corrupt_store(
    tmp_path: Path,
    api_name: str,
    call: Callable[[CronService], object],
) -> None:
    """Public APIs should report the corrupt store explicitly instead of
    leaking ``AttributeError`` when the first load cannot produce a store."""
    store_path = _corrupt_store(tmp_path)
    service = CronService(store_path)

    with pytest.raises(RuntimeError, match="corrupt.*restore jobs.json") as exc_info:
        call(service)

    assert api_name
    assert str(store_path) in str(exc_info.value)
    _assert_original_unchanged(store_path)


@pytest.mark.asyncio
async def test_run_job_raises_clear_error_and_restores_running_state_for_corrupt_store(
    tmp_path: Path,
) -> None:
    store_path = _corrupt_store(tmp_path)
    service = CronService(store_path)

    with pytest.raises(RuntimeError, match="corrupt.*restore jobs.json"):
        await service.run_job("missing")

    assert service._running is False
    _assert_original_unchanged(store_path)


@pytest.mark.asyncio
async def test_run_job_preserves_running_state_when_corrupt_store_unavailable(
    tmp_path: Path,
) -> None:
    store_path = _corrupt_store(tmp_path)
    service = CronService(store_path)
    service._running = True
    service._arm_timer = lambda: None

    with pytest.raises(RuntimeError, match="corrupt.*restore jobs.json"):
        await service.run_job("missing")

    assert service._running is True
    service.stop()


def test_running_add_job_raises_clear_error_for_unavailable_corrupt_store(
    tmp_path: Path,
) -> None:
    store_path = _corrupt_store(tmp_path)
    service = CronService(store_path)
    service._running = True

    with pytest.raises(RuntimeError, match="corrupt.*restore jobs.json"):
        service.add_job(
            name="running add",
            schedule=CronSchedule(kind="every", every_ms=60_000),
            message="hello",
            session_key="websocket:chat-1",
            origin_channel="websocket",
            origin_chat_id="chat-1",
        )

    _assert_original_unchanged(store_path)


def test_stopped_add_job_still_appends_action_without_loading_corrupt_store(
    tmp_path: Path,
) -> None:
    """The stopped-service add path is an action-log write and must not start
    requiring a readable store."""
    store_path = _corrupt_store(tmp_path)
    service = CronService(store_path)

    job = service.add_job(
        name="offline add",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        message="hello",
        session_key="websocket:chat-1",
        origin_channel="websocket",
        origin_chat_id="chat-1",
    )

    assert job.name == "offline add"
    assert store_path.exists()
    assert store_path.read_text(encoding="utf-8") == "{not valid json"
    assert list(store_path.parent.glob("jobs.json.corrupt-*")) == []
    actions = (store_path.parent / "action.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(actions) == 1
    assert json.loads(actions[0])["action"] == "add"




def test_full_round_trip_survives_repeated_save_load(tmp_path: Path) -> None:
    """Sanity check: jobs survive add → save → reload across fresh
    ``CronService`` instances pointing at the same store."""
    store_path = tmp_path / "cron" / "jobs.json"

    s1 = CronService(store_path)
    s1.add_job(
        name="Daily Loving Message",
        schedule=CronSchedule(kind="cron", expr="0 10 * * *", tz="Asia/Kuwait"),
        message="hello",
    )

    s2 = CronService(store_path)
    s2._load_store()
    assert s2._store is not None
    assert [j.name for j in s2._store.jobs] == ["Daily Loving Message"]


def test_malformed_action_does_not_erase_prior_valid_pending_actions(tmp_path):
    service, store_path = _seeded_store(tmp_path)
    service.add_job(name="Keep this pending job", schedule=CronSchedule(kind="every", every_ms=60_000), message="check", session_key="websocket:research", origin_channel="websocket", origin_chat_id="research")
    actions = store_path.parent / "action.jsonl"
    with actions.open("a") as stream:
        stream.write('{"action":"unrecognized","params":{}}\n')
    before_actions, before_store = actions.read_bytes(), store_path.read_bytes()
    owner = CronService(store_path)
    owner._running = True
    for _ in range(2):
        with pytest.raises(RuntimeError, match="Invalid automation action.*:2:"):
            owner.list_jobs()
        assert actions.read_bytes() == before_actions
        assert store_path.read_bytes() == before_store


@pytest.mark.asyncio
async def test_failed_due_tick_reports_to_owner_and_waits_before_retry(tmp_path):
    failures, rearmed = [], []
    service, store_path = _seeded_store(tmp_path)
    service.on_error = failures.append
    service._running = True
    service._arm_timer = lambda **options: rearmed.append(options)
    store_path.write_text("{not valid json")
    await service._run_timer()
    assert len(failures) == 1
    assert "corrupt" in str(failures[0])
    assert rearmed == [{"retry": True}]
    assert service._active_executions == 0
    _assert_original_unchanged(store_path)
