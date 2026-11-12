"""Serial SSH job monitoring and terminal-record retention, without LLM calls."""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timezone

from loguru import logger

from cirno_core.nodes.jobs import NodeJobs
from cirno_core.nodes.policy import ACTIVE_JOB_STATES, TERMINAL_JOB_STATES, NodeJobPolicy, read_policy
from cirno_core.nodes.service import Nodes
from cirno_core.storage.instance import InstanceData


def timestamp(value: str | None) -> float:
    if not value:
        return 0
    parsed = datetime.fromisoformat(value)
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()


def prune_records(data: InstanceData, policy: NodeJobPolicy, now: datetime) -> int:
    if policy.retention_days == 0:
        return 0
    cutoff = now.timestamp() - policy.retention_days * 86400
    removed = 0
    with data.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for identifier, body in connection.execute("SELECT id,body FROM records WHERE kind='node_jobs'").fetchall():
            job = json.loads(body)
            if job.get("state") not in TERMINAL_JOB_STATES:
                continue
            if not job.get("finished_at"):
                # Legacy records have no reliable completion time. Start their
                # retention window when first observed, not at submission time.
                job["finished_at"] = now.isoformat()
                connection.execute("UPDATE records SET body=? WHERE kind='node_jobs' AND id=?", (json.dumps(job, ensure_ascii=False), identifier))
            elif timestamp(job["finished_at"]) < cutoff:
                connection.execute("DELETE FROM records WHERE kind='node_jobs' AND id=?", (identifier,))
                removed += 1
    return removed


class NodeJobMonitor:
    def __init__(self, nodes: Nodes):
        self.nodes = nodes
        self.jobs = NodeJobs(nodes)
        self._pruned_at: float | None = None

    async def cycle(self, policy: NodeJobPolicy, *, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if self._pruned_at is None or time.monotonic() - self._pruned_at >= 60:
            await asyncio.to_thread(prune_records, self.nodes.data, policy, now)
            self._pruned_at = time.monotonic()
        if policy.poll_interval_seconds == 0:
            return
        grouped: dict[str, list[dict]] = defaultdict(list)
        records = await asyncio.to_thread(self.nodes.data.list, "node_jobs")
        for job in records:
            checked = timestamp(job.get("check_started_at") or job.get("created_at"))
            if job["state"] in ACTIVE_JOB_STATES and now.timestamp() - checked >= policy.poll_interval_seconds:
                grouped[job["node_id"]].append(job)
        for node_jobs in grouped.values():
            # Bound remote command length and response size while sharing a
            # connection across jobs on the same Node. Never overlap batches.
            for offset in range(0, len(node_jobs), 32):
                batch = node_jobs[offset:offset + 32]
                started = datetime.now(timezone.utc)
                try:
                    await self.jobs.inspect_jobs(batch, started)
                except (RuntimeError, OSError, TimeoutError, ValueError, KeyError) as error:
                    logger.warning("Node job status check failed for {}: {}", batch[0]["node_id"], error)
                    await self.jobs.record_check_error(batch, started, error)

    async def run(self) -> None:
        while True:
            try:
                policy = await asyncio.to_thread(read_policy, self.nodes.data)
                await self.cycle(policy)
            except Exception:
                # A storage/configuration failure must be visible, and must not
                # stop the chat server or turn a failed check into a completion.
                logger.exception("Node job maintenance failed")
                await asyncio.sleep(5)
                continue
            await asyncio.sleep(min(5, policy.poll_interval_seconds or 5))


async def monitor_node_jobs() -> None:
    await NodeJobMonitor(await asyncio.to_thread(Nodes)).run()
