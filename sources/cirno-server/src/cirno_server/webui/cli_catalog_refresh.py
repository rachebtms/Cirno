"""Runtime-owned CLI catalog refresh, throttle and shutdown lifetime."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from cirno_core.apps.cli import CliAppManager
from cirno_core.runtime.admission import RuntimeAdmission
from cirno_core.utils.cancellation import shield_and_drain
from loguru import logger

_CATALOG_REFRESH_RETRY_SECONDS = 60.0


class CliCatalogRefresh:
    """Keep one settings owner's detached catalog writer visible to maintenance."""

    def __init__(self, admission: RuntimeAdmission) -> None:
        self._admission = admission
        self._task: asyncio.Task[None] | None = None
        self._last_started: float | None = None
        self._remove_pending: Callable[[], None] | None = None
        self._closed = False

    @property
    def has_pending_work(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, manager: CliAppManager) -> bool:
        if self._closed:
            return False
        self._admission.check()
        if self.has_pending_work:
            return True
        now = time.monotonic()
        if self._last_started is not None and now - self._last_started < _CATALOG_REFRESH_RETRY_SECONDS:
            return False
        if self._remove_pending is None:
            self._remove_pending = self._admission.register_pending_work(lambda: self.has_pending_work)
        self._last_started = now
        self._task = asyncio.create_task(self._refresh(manager))
        return True

    @staticmethod
    async def _refresh(manager: CliAppManager) -> None:
        try:
            await manager.registry.refresh_catalog_cache(force_refresh=True)
        except Exception:
            logger.exception("CLI Apps catalog refresh failed; retaining the cached catalog")

    async def close(self) -> None:
        self._closed = True
        task = self._task
        if task is not None and not task.done() and not task.cancelling():
            task.cancel()
        try:
            if task is not None:
                await shield_and_drain(asyncio.gather(task, return_exceptions=True))
        finally:
            if not self.has_pending_work and self._remove_pending is not None:
                self._remove_pending()
                self._remove_pending = None
