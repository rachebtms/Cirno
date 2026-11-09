"""A scheduled occurrence and Run now must not execute the same job together."""

import asyncio

import pytest

from cirno_core.cron.service import CronService
from cirno_core.cron.types import CronSchedule


@pytest.mark.parametrize("first_timer,second_timer", [(False, False), (True, False), (False, True)])
async def test_same_job_cannot_overlap_and_can_run_again_after_completion(
    tmp_path, first_timer, second_timer,
):
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def execute(job):
        calls.append(job.id)
        entered.set()
        await release.wait()

    service = CronService(tmp_path / "jobs.json", on_job=execute)
    job = service.add_job(
        "Report", CronSchedule(kind="every", every_ms=60_000), "Summarize",
        session_key="websocket:worker", origin_channel="websocket", origin_chat_id="worker",
    )
    await service.start()
    service.stop()
    # Make the scheduled occurrence due and keep that exact catalog live.
    service._store = service._load_store()
    service._store.jobs[0].state.next_run_at_ms = 1
    service._save_store()
    first = asyncio.create_task(service._run_timer() if first_timer else service.run_job(job.id))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        if second_timer:
            await asyncio.wait_for(service._run_timer(), 1)
        else:
            with pytest.raises(ValueError, match="already running"):
                await asyncio.wait_for(service.run_job(job.id), 1)
        assert calls == [job.id]
    finally:
        release.set()
        await first
        service.stop()
    assert len(service.get_job(job.id).state.run_history) == 1
    assert await service.run_job(job.id)
    assert calls == [job.id, job.id]

