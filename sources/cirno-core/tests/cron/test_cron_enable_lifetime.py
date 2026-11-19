"""Explicit enable/disable transitions own the next occurrence during a run."""

import asyncio

import pytest
from cirno_core.cron.service import CronService
from cirno_core.cron.types import CronSchedule


@pytest.mark.parametrize("finish_enabled", [False, True])
@pytest.mark.parametrize("kind", ["every", "at"])
async def test_running_completion_preserves_the_latest_enable_transition(
    tmp_path, monkeypatch, finish_enabled, kind
):
    now = 1_900_000_000_000
    monkeypatch.setattr("cirno_core.cron.service._now_ms", lambda: now)
    entered, release = asyncio.Event(), asyncio.Event()

    async def execute(job):
        entered.set()
        await release.wait()

    service = CronService(tmp_path / "jobs.json", on_job=execute)
    schedule = (
        CronSchedule(kind="at", at_ms=now + 60000)
        if kind == "at"
        else CronSchedule(kind="every", every_ms=60000)
    )
    job = service.add_job(
        "Report",
        schedule,
        "Summarize",
        session_key="websocket:report",
        origin_channel="websocket",
        origin_chat_id="report",
        delete_after_run=kind == "at",
    )
    task = asyncio.create_task(service.run_job(job.id))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        now += 1000
        service.enable_job(job.id, False)
        if finish_enabled:
            service.enable_job(job.id, True)
        current = service.get_job(job.id)
        expected = current.state.next_run_at_ms
        now += 10000
        release.set()
        assert await task
        saved = service.get_job(job.id)
        assert saved.enabled is finish_enabled
        assert saved.state.next_run_at_ms == expected
        assert len(saved.state.run_history) == 1
        assert saved.state.last_status == "ok"
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("enabled", [False, True])
def test_repeating_an_enable_state_does_not_reschedule_or_rewrite(tmp_path, monkeypatch, enabled):
    now = 1_900_000_000_000
    monkeypatch.setattr("cirno_core.cron.service._now_ms", lambda: now)
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        "Report",
        CronSchedule(kind="every", every_ms=60000),
        "Summarize",
        session_key="websocket:report",
        origin_channel="websocket",
        origin_chat_id="report",
    )
    if not enabled:
        service.enable_job(job.id, False)
    before = service.get_job(job.id)
    next_run, updated = before.state.next_run_at_ms, before.updated_at_ms
    actions = service._action_path.read_bytes()
    now += 10000
    result = service.enable_job(job.id, enabled)
    assert result.state.next_run_at_ms == next_run
    assert result.updated_at_ms == updated
    assert service._action_path.read_bytes() == actions
