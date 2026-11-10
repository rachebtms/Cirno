"""One bounded memory-maintenance pass in idle slots; no extra scheduler process."""
import asyncio
import time

from cirno_core.config.home import get_home_path
from cirno_memory.repository import MemoryRepository
from loguru import logger


class MemoryIdleCoordinator:
    def __init__(self, agent, config):
        self.agent, self.config = agent, config
        self.next_scan = 0.0

    async def check(self):
        agent = self.agent
        if agent.bus.admission.paused or agent._active_tasks or agent._background_tasks or agent.bus.has_pending_events:
            return
        current = time.monotonic()
        if current >= self.next_scan:
            self.next_scan = current + 60
            def maintain():
                repo = MemoryRepository(get_home_path())
                repo.sync_profiles()
                repo.reconcile(limit=self.config.agents.defaults.memory.index_scan_batch)
            try:
                await asyncio.to_thread(maintain)
            except (OSError, ValueError) as exc:
                logger.warning("Memory maintenance: {}", exc)
