"""Startup reconciliation retains system task history across configuration edits."""

from dataclasses import asdict

import pytest
from cirno_core.cron.service import CronService
from cirno_core.cron.types import CronJob, CronPayload, CronSchedule


@pytest.mark.parametrize("changed_interval", [False, True])
async def test_reregister_system_job_preserves_execution_history(
    tmp_path, monkeypatch, changed_interval
):
    now = 1_900_000_000_000
    monkeypatch.setattr("cirno_core.cron.service._now_ms", lambda: now)

    def heartbeat(interval):
        return CronJob(
            id="heartbeat",
            name="heartbeat",
            schedule=CronSchedule(kind="every", every_ms=interval),
            payload=CronPayload(kind="system_event"),
        )

    async def execute(_job):
        raise RuntimeError("Previous heartbeat failed")

    service = CronService(tmp_path / "jobs.json", on_job=execute)
    service.register_system_job(heartbeat(60000))
    now += 1000
    assert await service.run_job("heartbeat")
    previous = service.get_job("heartbeat")
    history = asdict(previous.state)
    now += 10000
    restarted = CronService(service.store_path)
    updated = restarted.register_system_job(heartbeat(120000 if changed_interval else 60000))
    assert updated.created_at_ms == previous.created_at_ms
    assert updated.updated_at_ms == now
    assert updated.state.last_run_at_ms == previous.state.last_run_at_ms
    assert updated.state.last_status == "error"
    assert updated.state.last_error == "Previous heartbeat failed"
    assert asdict(updated.state)["run_history"] == history["run_history"]
    assert updated.state.next_run_at_ms == (
        now + 120000 if changed_interval else history["next_run_at_ms"]
    )
    persisted = CronService(service.store_path).get_job("heartbeat")
    assert asdict(persisted) == asdict(updated)
