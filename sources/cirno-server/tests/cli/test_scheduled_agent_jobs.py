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
        agent, MagicMock(), report=MagicMock()
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
    assert jobs.agent.bus.inbound_size == 0


async def test_retired_dream_job_never_starts_an_independent_model_run(jobs):
    from cirno_core.cron.service import CronJobSkippedError
    job = CronJob(id="dream", name="Memory upkeep", payload=CronPayload(kind="system_event"))
    with pytest.raises(CronJobSkippedError, match="Unknown system job"):
        await jobs.execute(job)
    agent_jobs.run_bound_cron_job.assert_not_awaited()


def test_register_removes_persisted_dream_job_and_keeps_heartbeat(jobs):
    from cirno_core.config.schema import Config
    jobs.cron.status.return_value = {"jobs": 1}
    jobs.register(Config())
    jobs.cron.remove_system_job.assert_any_call("dream")
    assert all(call.args[0].id != "dream" for call in jobs.cron.register_system_job.call_args_list)
    assert jobs.agent.memory_idle_callback is not None


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
