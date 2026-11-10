"""Compose system maintenance and conversation-bound scheduled execution."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import cast

from cirno_core.agent.loop import AgentLoop
from cirno_core.config.schema import Config
from cirno_core.cron.bound_runner import run_bound_cron_job
from cirno_core.cron.service import CronJobSkippedError, CronService
from cirno_core.cron.session_turns import is_bound_cron_job
from cirno_core.cron.types import CronJob, CronPayload, CronRunResult, CronSchedule
from cirno_core.runtime.heartbeat import has_active_tasks
from loguru import logger


class ScheduledAgentJobs:
    def __init__(
        self,
        agent: AgentLoop,
        cron: CronService,
        *,
        report: Callable[[str], None],
    ):
        self.agent, self.cron, self.report = agent, cron, report
        self._system_jobs = {"heartbeat": self.heartbeat}

    async def execute(self, job: CronJob) -> str | CronRunResult | None:
        """Execute a cron job through the agent."""

        if job.payload.kind == "system_event":
            handler = self._system_jobs.get(job.id)
            if handler is None:
                raise CronJobSkippedError(f"Unknown system job: {job.id}")
            await handler()
            return None

        if is_bound_cron_job(job):
            return await run_bound_cron_job(job, agent=self.agent, cron=self.cron)

        reason = "unbound agent cron job must be recreated from a chat session"
        logger.warning(
            "Cron: skipped unbound agent job '{}' ({}): {}",
            job.name,
            job.id,
            reason,
        )
        raise CronJobSkippedError(reason)

    async def heartbeat(self) -> None:
        from cirno_core.config.home import get_home_path
        from cirno_core.runtime.heartbeat import enqueue_heartbeat, heartbeat_paused

        if await heartbeat_paused(self.agent.sessions):
            return
        heartbeat_file = get_home_path() / "HEARTBEAT.md"
        try:
            content = await asyncio.to_thread(heartbeat_file.read_text, encoding="utf-8")
        except FileNotFoundError:
            logger.debug("Heartbeat: HEARTBEAT.md missing")
            return
        if not has_active_tasks(content):
            logger.debug("Heartbeat: HEARTBEAT.md has no active tasks")
            return
        queued = await enqueue_heartbeat(self.agent.sessions, self.agent.bus, content)
        logger.info(
            "Heartbeat: {}", "queued for the Router" if queued else "already pending in the Router"
        )

    def register(self, config: Config) -> None:
        hb_cfg = config.agents.defaults.heartbeat
        # Old persisted jobs must not survive the unified, inline learning flow.
        self.cron.remove_system_job("dream")
        from cirno_core.memory.idle import MemoryIdleCoordinator

        memory_idle = MemoryIdleCoordinator(self.agent, config)
        self.agent.memory_idle_callback = memory_idle.check
        self.report("Context consolidation: checkpoint and learning in one request")

        # Register Heartbeat system job (idempotent on restart)
        if hb_cfg.enabled:
            self.cron.register_system_job(
                CronJob(
                    id="heartbeat",
                    name="heartbeat",
                    schedule=CronSchedule(
                        kind="every",
                        every_ms=hb_cfg.interval_s * 1000,
                        tz=config.agents.defaults.timezone,
                    ),
                    payload=CronPayload(kind="system_event"),
                )
            )
        else:
            self.cron.remove_system_job("heartbeat")

        cron_status = self.cron.status()
        cron_job_count = cast(int, cron_status["jobs"])
        if cron_job_count > 0:
            self.report(f"[green]✓[/green] Cron: {cron_job_count} scheduled jobs")
