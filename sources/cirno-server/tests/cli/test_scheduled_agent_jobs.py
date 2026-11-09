"""Scheduled routes use payload identity; file failures remain visible."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.bus.queue import MessageBus
from cirno_core.cron.types import CronJob, CronPayload, CronRunResult
from cirno_server.scheduling import agent_jobs


@pytest.fixture
def jobs(monkeypatch):
    sessions = MagicMock()
    sessions.state.read_metadata = AsyncMock(return_value=None)
    agent = SimpleNamespace(sessions=sessions, bus=MessageBus())
    owner = agent_jobs.ScheduledAgentJobs(
        agent, MagicMock(), prepare=AsyncMock(), report=MagicMock()
    )
    monkeypatch.setattr(
        agent_jobs, "run_dream", AsyncMock(return_value=SimpleNamespace(status="empty", reason=""))
    )
    monkeypatch.setattr(
        agent_jobs,
        "run_bound_cron_job",
        AsyncMock(return_value=CronRunResult("run-id", "Complete")),
    )
    return owner


@pytest.mark.parametrize("name", ["dream", "heartbeat"])
async def test_user_task_name_cannot_route_it_into_system_maintenance(jobs, name):
    job = CronJob(
        id="user-job",
        name=name,
        payload=CronPayload(
            kind="agent_turn",
            session_key="websocket:worker",
            origin_channel="websocket",
            origin_chat_id="worker",
        ),
    )
    result = await jobs.execute(job)
    assert result is agent_jobs.run_bound_cron_job.return_value
    agent_jobs.run_bound_cron_job.assert_awaited_once_with(job, agent=jobs.agent, cron=jobs.cron)
    agent_jobs.run_dream.assert_not_awaited()
    assert jobs.agent.bus.inbound_size == 0


async def test_system_task_route_survives_a_display_name_change(jobs):
    job = CronJob(id="dream", name="Memory upkeep", payload=CronPayload(kind="system_event"))
    assert await jobs.execute(job) is None
    agent_jobs.run_dream.assert_awaited_once()
    agent_jobs.run_bound_cron_job.assert_not_awaited()


async def test_heartbeat_permission_error_is_not_reported_as_a_missing_file(jobs, monkeypatch):
    original = Path.read_text
    problem = PermissionError("Fixture heartbeat cannot be read")

    def read(path, *args, **kwargs):
        if path.name == "HEARTBEAT.md":
            raise problem
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    job = CronJob(id="heartbeat", name="heartbeat", payload=CronPayload(kind="system_event"))
    with pytest.raises(PermissionError) as caught:
        await jobs.execute(job)
    assert caught.value is problem
    assert jobs.agent.bus.inbound_size == 0
