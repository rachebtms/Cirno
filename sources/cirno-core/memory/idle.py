"""One bounded memory-maintenance pass in idle slots; no extra scheduler process."""
import asyncio
import time

from cirno.config.home import get_home_path
from cirno.memory.repository import MemoryRepository
from loguru import logger


class MemoryIdleCoordinator:
    def __init__(self, agent, config, run_dream):
        self.agent, self.config, self.run_dream = agent, config, run_dream
        self.next_scan = 0.0
        self.next_dream = 0.0

    async def check(self):
        agent = self.agent
        if agent.bus.admission.paused or agent._active_tasks or agent._background_tasks or agent.bus.has_pending_events:
            return
        current = time.monotonic()
        if current >= self.next_scan:
            self.next_scan = current + 60
            def maintain():
                repo = MemoryRepository(get_home_path())
                repo.migrate_legacy()
                repo.sync_profiles()
                repo.reconcile(limit=self.config.agents.defaults.memory.index_scan_batch)
            try:
                await asyncio.to_thread(maintain)
            except (OSError, ValueError) as exc:
                logger.warning("Memory maintenance: {}", exc)
        cfg = self.config.agents.defaults.dream
        if (not cfg.enabled or cfg.mode != "idle" or current < self.next_dream
                or current - agent._last_memory_activity < cfg.idle_after_seconds):
            return
        # Back off even for an empty queue or provider failure; foreground dispatch cancels this task.
        self.next_dream = current + max(60, cfg.idle_after_seconds)
        agent._idle_memory_task = agent.schedule_background(self.run_dream())
