"""The final persistence boundary must recheck near-future one-shot times."""

from dataclasses import asdict
from datetime import datetime, timezone

import pytest
from cirno_core.agent.tools.cron import CronTool
from cirno_core.cron.service import CronService
from cirno_core.cron.types import CronSchedule


@pytest.mark.parametrize("action", ["add", "update"])
async def test_expiring_schedule_between_parse_and_persistence_does_not_change_store(
    tmp_path, monkeypatch, action
):
    now = 1_900_000_000_000
    monkeypatch.setattr("cirno_core.agent.tools.cron.time.time", lambda: 1_900_000_000)
    monkeypatch.setattr("cirno_core.cron.service._now_ms", lambda: now)
    service = CronService(tmp_path / "jobs.json")
    job = service.add_job(
        "Original",
        CronSchedule(kind="every", every_ms=60000),
        "Keep this instruction",
        session_key="websocket:report",
        origin_channel="websocket",
        origin_chat_id="report",
    )
    before = asdict(service.get_job(job.id))
    actions = service._action_path.read_bytes()
    tool = CronTool(service)
    monkeypatch.setattr(
        tool, "_request_route", lambda: ("websocket:report", "websocket", "report", {})
    )
    parse = tool._parse_schedule

    def expire(*args):
        nonlocal now
        schedule = parse(*args)
        assert isinstance(schedule, CronSchedule)
        now += 2000
        return schedule

    monkeypatch.setattr(tool, "_parse_schedule", expire)
    at = datetime.fromtimestamp((now + 1000) / 1000, tz=timezone.utc).isoformat()
    result = await tool.execute(
        action=action,
        job_id=job.id if action == "update" else None,
        name="Rejected name",
        message="Rejected instructions",
        at=at,
    )
    assert getattr(result, "is_error", False)
    assert "future occurrence" in result
    assert [asdict(item) for item in service.list_jobs(include_disabled=True)] == [before]
    assert service._action_path.read_bytes() == actions
