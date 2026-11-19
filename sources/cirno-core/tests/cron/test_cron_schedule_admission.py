"""One-shot admission cannot report success for an unusable instant."""

from dataclasses import asdict
from datetime import datetime, timezone

import pytest
from cirno_core.agent.tools.cron import CronTool
from cirno_core.cron.service import CronService
from cirno_core.cron.types import CronSchedule


async def test_tool_cannot_enable_expired_one_shot(tmp_path, monkeypatch):
    now = 1_900_000_000_000
    monkeypatch.setattr("cirno_core.cron.service._now_ms", lambda: now)
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        "Reminder",
        CronSchedule(kind="at", at_ms=now + 1000),
        "Send report",
        session_key="websocket:report",
        origin_channel="websocket",
        origin_chat_id="report",
    )
    service.enable_job(job.id, False)
    before = asdict(service.get_job(job.id))
    actions = service._action_path.read_bytes()
    now += 2000
    result = await CronTool(service).execute(action="enable", job_id=job.id)
    assert getattr(result, "is_error", False)
    assert "future occurrence" in result
    assert asdict(service.get_job(job.id)) == before
    assert service._action_path.read_bytes() == actions
    service.update_job(job.id, schedule=CronSchedule(kind="at", at_ms=now + 1000))
    result = await CronTool(service).execute(action="enable", job_id=job.id)
    assert not getattr(result, "is_error", False)
    assert service.get_job(job.id).state.next_run_at_ms == now + 1000


@pytest.mark.parametrize("wall_time", ["2030-03-10T02:30:00", "2030-03-10T02:30:00.123456"])
async def test_tool_rejects_nonexistent_dst_time_without_modifying_job(
    tmp_path, monkeypatch, wall_time
):
    monkeypatch.setattr("cirno_core.agent.tools.cron.time.time", lambda: 1_700_000_000)
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        "Reminder",
        CronSchedule(kind="every", every_ms=60000),
        "Send report",
        session_key="websocket:report",
        origin_channel="websocket",
        origin_chat_id="report",
    )
    before = asdict(service.get_job(job.id))
    result = await CronTool(service, default_timezone="America/New_York").execute(
        action="update",
        job_id=job.id,
        name="Wrong time",
        at=wall_time,
    )
    assert getattr(result, "is_error", False)
    assert "does not exist" in result
    assert asdict(service.get_job(job.id)) == before


@pytest.mark.parametrize("at", ["2030-03-10T03:30:00.123456", "2030-03-10T02:30:00.123456-05:00"])
def test_tool_keeps_valid_local_or_explicit_offset_time(tmp_path, monkeypatch, at):
    monkeypatch.setattr("cirno_core.agent.tools.cron.time.time", lambda: 1_700_000_000)
    tool = CronTool(CronService(tmp_path / "jobs.json"), default_timezone="America/New_York")
    schedule = tool._parse_schedule(None, None, None, at)
    assert isinstance(schedule, CronSchedule)
    expected = datetime(2030, 3, 10, 7, 30, 0, 123456, tzinfo=timezone.utc)
    assert schedule.at_ms == int(expected.timestamp() * 1000)
