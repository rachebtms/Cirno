"""Compose system maintenance and conversation-bound scheduled execution."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

from cirno_core.agent.loop import AgentLoop
from cirno_core.config.schema import Config
from cirno_core.cron.bound_runner import run_bound_cron_job
from cirno_core.cron.service import CronJobSkippedError, CronService
from cirno_core.cron.session_turns import is_bound_cron_job
from cirno_core.cron.types import CronJob, CronPayload, CronRunResult, CronSchedule
from cirno_core.memory.dream_run import run_dream
from cirno_core.runtime.heartbeat import has_active_tasks
from loguru import logger


class ScheduledAgentJobs:
    def __init__(
        self,
        agent: AgentLoop,
        cron: CronService,
        *,
        prepare: Callable[[], Awaitable[None]],
        report: Callable[[str], None],
    ):
        self.agent, self.cron, self.prepare, self.report = agent, cron, prepare, report
        self._system_jobs = {"dream": self.dream, "heartbeat": self.heartbeat}

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

    async def dream(self) -> None:
        result = await run_dream(
            self.agent,
            commit_subject="dream: periodic memory consolidation",
            prepare=self.prepare,
        )
        logger.info("Dream {}: {}", result.status, result.reason)

    async def heartbeat(self) -> None:
        from cirno_core.config.home import get_home_path
        from cirno_core.runtime.heartbeat import enqueue_heartbeat

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
        # Register Dream system job (idempotent on restart)

        dream_cfg = config.agents.defaults.dream
        if dream_cfg.enabled and dream_cfg.mode == "interval":
            self.cron.register_system_job(
                CronJob(
                    id="dream",
                    name="dream",
                    schedule=dream_cfg.build_schedule(config.agents.defaults.timezone),
                    payload=CronPayload(kind="system_event"),
                )
            )
            self.report(f"[green]✓[/green] Dream: {dream_cfg.describe_schedule()}")
        else:
            self.report(
                f"Dream: {dream_cfg.describe_schedule() if dream_cfg.enabled else 'disabled'}"
            )
            self.cron.remove_system_job("dream")

        from cirno_core.memory.idle import MemoryIdleCoordinator

        memory_idle = MemoryIdleCoordinator(self.agent, config, self.dream)
        self.agent.memory_idle_callback = memory_idle.check

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
