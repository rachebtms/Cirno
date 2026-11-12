"""Background SSH checks and retention do not depend on a browser or model."""

import asyncio
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from cirno_core.nodes.jobs import NodeJobs
from cirno_core.nodes.monitor import NodeJobMonitor, prune_records
from cirno_core.nodes.policy import ACTIVE_JOB_STATES, TERMINAL_JOB_STATES, NodeJobPolicy, read_policy, save_policy
from cirno_core.nodes.service import Nodes
from cirno_core.storage.instance import InstanceData


def service(tmp_path):
    return Nodes(InstanceData(tmp_path))


def record(nodes, state="running", node="gpu", **values):
    return nodes.data.save("node_jobs", {"node_id": node, "state": state, "created_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(), **values})


def identifiers(script):
    return re.findall(r"printf '%s ' ([a-f0-9]+);", script)


async def test_many_jobs_share_serial_connections_and_terminal_jobs_are_not_polled(tmp_path):
    nodes = service(tmp_path)
    active = [record(nodes) for _ in range(35)] + [record(nodes, "submission_unknown", "other")]
    finished = record(nodes, "completed")
    inflight = peak = 0

    async def execute(node, script, **kwargs):
        nonlocal inflight, peak
        inflight += 1; peak = max(peak, inflight)
        await asyncio.sleep(0)
        assert "tail -c" not in script and "nohup" not in script
        inflight -= 1
        return "".join(f"{identifier} EXIT:0\n" for identifier in identifiers(script))

    nodes.execute = AsyncMock(side_effect=execute)
    monitor = NodeJobMonitor(nodes)
    await monitor.cycle(NodeJobPolicy(retention_days=0))
    assert nodes.execute.await_count == 3 and peak == 1
    assert finished["id"] not in str(nodes.execute.call_args_list)
    for job in active:
        saved = nodes.data.get("node_jobs", job["id"])
        assert saved["state"] == "completed" and saved["exit_code"] == 0
        assert saved["checked_at"] and saved["finished_at"]
    await monitor.cycle(NodeJobPolicy(retention_days=0))
    assert nodes.execute.await_count == 3


async def test_disconnect_keeps_last_state_and_recovery_clears_the_check_error(tmp_path):
    nodes = service(tmp_path)
    job = record(nodes, output="previous output")
    now = datetime.now(timezone.utc)
    nodes.execute = AsyncMock(side_effect=RuntimeError("Connection to frps closed"))
    monitor = NodeJobMonitor(nodes)
    policy = NodeJobPolicy(poll_interval_seconds=60, retention_days=0)
    await monitor.cycle(policy, now=now)
    failed = nodes.data.get("node_jobs", job["id"])
    assert failed["state"] == "running" and failed["output"] == "previous output"
    assert "frps" in failed["check_error"] and "checked_at" not in failed
    await monitor.cycle(policy, now=now + timedelta(seconds=30))
    assert nodes.execute.await_count == 1
    nodes.execute.side_effect = None
    nodes.execute.return_value = f"{job['id']} EXIT:2\n"
    await monitor.cycle(policy, now=now + timedelta(seconds=61))
    final = nodes.data.get("node_jobs", job["id"])
    assert final["state"] == "failed" and final["exit_code"] == 2
    assert "check_error" not in final


async def test_stale_background_observation_cannot_undo_a_newer_manual_completion(tmp_path):
    nodes = service(tmp_path)
    job = record(nodes)
    jobs = NodeJobs(nodes)
    earlier = datetime.now(timezone.utc) - timedelta(seconds=1)
    later = datetime.now(timezone.utc)
    final = await jobs._observe(job, "EXIT:0", later, output="finished")
    stale = await jobs._observe(job, "RUNNING", earlier)
    await jobs.record_check_error([job], earlier, RuntimeError("old disconnection"))
    assert stale == final == nodes.data.get("node_jobs", job["id"])


@pytest.mark.parametrize("state", sorted(TERMINAL_JOB_STATES))
def test_retention_uses_completion_time_and_keeps_active_and_uncertain_jobs(tmp_path, state):
    nodes = service(tmp_path)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=40)).isoformat()
    expired = record(nodes, state, finished_at=old, output="cached log")
    recent = record(nodes, state, created_at=old, finished_at=now.isoformat())
    legacy = record(nodes, state, created_at=old)
    active = [record(nodes, pending, created_at=old, finished_at=old) for pending in ACTIVE_JOB_STATES]
    assert prune_records(nodes.data, NodeJobPolicy(retention_days=30), now) == 1
    remaining = {job["id"] for job in nodes.data.list("node_jobs")}
    assert expired["id"] not in remaining
    assert {recent["id"], legacy["id"], *(job["id"] for job in active)} <= remaining
    assert nodes.data.get("node_jobs", legacy["id"])["finished_at"] == now.isoformat()


async def test_zero_disables_checks_and_retains_terminal_records_indefinitely(tmp_path):
    nodes = service(tmp_path)
    record(nodes)
    finished = record(nodes, "completed", finished_at="2020-01-01T00:00:00+00:00")
    nodes.execute = AsyncMock()
    await NodeJobMonitor(nodes).cycle(NodeJobPolicy(poll_interval_seconds=0, retention_days=0))
    nodes.execute.assert_not_called()
    assert nodes.data.get("node_jobs", finished["id"])["state"] == "completed"


async def test_cancelling_the_monitor_does_not_stop_or_relaunch_remote_work(tmp_path):
    nodes = service(tmp_path)
    job = record(nodes)
    entered = asyncio.Event()

    async def wait(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    nodes.execute = AsyncMock(side_effect=wait)
    task = asyncio.create_task(NodeJobMonitor(nodes).run())
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert nodes.execute.await_count == 1
    assert nodes.data.get("node_jobs", job["id"])["state"] == "running"


def test_policy_defaults_persist_and_partial_updates_preserve_other_settings(tmp_path):
    nodes = service(tmp_path)
    assert read_policy(nodes.data) == NodeJobPolicy(poll_interval_seconds=60, retention_days=30)
    save_policy(nodes.data, {"retention_days": 0})
    save_policy(nodes.data, {"poll_interval_seconds": 10})
    restored = read_policy(InstanceData(tmp_path))
    assert restored.poll_interval_seconds == 10 and restored.retention_days == 0


@pytest.mark.parametrize("values", [{"retention_days": -1}, {"poll_interval_seconds": 1.5}, {"retention_days": True}, {"unexpected": 5}])
def test_invalid_policy_update_keeps_previous_values(tmp_path, values):
    data = InstanceData(tmp_path)
    save_policy(data, {"retention_days": 7})
    with pytest.raises(ValidationError):
        save_policy(data, values)
    assert read_policy(data).retention_days == 7


async def test_late_submission_ack_cannot_regress_an_already_observed_completion(tmp_path):
    from cirno_core.nodes.service import Node
    nodes = service(tmp_path)
    nodes.node = lambda _: Node(name="GPU", host="server", username="owner")
    entered, release = asyncio.Event(), asyncio.Event()

    async def execute(*args, **kwargs):
        entered.set()
        await release.wait()
        return "1234"

    nodes.execute = execute
    task = asyncio.create_task(nodes.start_job("gpu", "train"))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        job = nodes.data.list("node_jobs")[0]
        await NodeJobs(nodes)._observe(job, "EXIT:0", datetime.now(timezone.utc), output="finished while acknowledgement was delayed")
        release.set()
        result = await task
        assert result["state"] == "completed" and result["output"].startswith("finished while")
        assert result["finished_at"] and result["exit_code"] == 0
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_expired_record_is_not_resurrected_by_a_late_status_reply(tmp_path):
    nodes = service(tmp_path)
    now = datetime.now(timezone.utc)
    job = record(nodes, "completed", finished_at=(now - timedelta(days=40)).isoformat())
    assert prune_records(nodes.data, NodeJobPolicy(retention_days=30), now) == 1
    with pytest.raises(KeyError):
        await NodeJobs(nodes)._observe(job, "EXIT:0", now)
    assert nodes.data.list("node_jobs") == []


async def test_launch_snapshot_cannot_restore_a_cleared_status_check_error(tmp_path):
    nodes = service(tmp_path)
    job = record(nodes, check_error="old network failure", output="old output")
    jobs = NodeJobs(nodes)
    final = await jobs._observe(job, "EXIT:0", datetime.now(timezone.utc), output="finished")
    saved = await jobs._save_job({**job, "pid": 1234})
    assert saved["state"] == "completed" and saved["output"] == "finished"
    assert saved["finished_at"] == final["finished_at"] and "check_error" not in saved
