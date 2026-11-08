"""Bounded session admission, ordered workers and cancellation-safe shutdown."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from cirno_core.session.sqlite_store import SqliteSessionStore
from cirno_core.utils.cancellation import shield_and_drain

_T = TypeVar("_T")
DEFAULT_CAPACITY = 64
DEFAULT_WORKERS = 4


class SessionOperationQueueFullError(RuntimeError):
    """The bounded session owner cannot admit another operation."""


class SessionOperations:
    """Own accepted work and the SQLite connections used by its executor threads."""

    def __init__(
        self,
        store: SqliteSessionStore,
        *,
        capacity: int = DEFAULT_CAPACITY,
        workers: int = DEFAULT_WORKERS,
    ) -> None:
        if capacity < 1:
            raise ValueError("session operation capacity must be positive")
        if workers < 1:
            raise ValueError("session operation worker count must be positive")
        self._store = store
        self._connection_lock = threading.Lock()
        self._capacity = capacity
        self._admitted = 0
        self._key_tails: dict[str, asyncio.Task[Any]] = {}
        self._global_tail: asyncio.Task[Any] | None = None
        self._pending: set[asyncio.Task[Any]] = set()
        self._connections: list[sqlite3.Connection] = []
        self._worker = ThreadPoolExecutor(
            max_workers=min(workers, capacity), thread_name_prefix="session-read"
        )
        self._writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="session-write")
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_bound(self) -> bool:
        """Whether runtime operations have claimed this state owner."""
        return self._loop is not None

    @property
    def bound_loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop

    def _bind_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError("session state belongs to a different event loop")

    def _worker_operation(self, operation: Callable[[], _T]) -> _T:
        connection = self._store.worker_connection()
        with self._connection_lock:
            if connection not in self._connections:
                self._connections.append(connection)
        return operation()

    async def run(self, operation: Callable[[], _T], *, write: bool) -> _T:
        return await asyncio.get_running_loop().run_in_executor(
            self._writer if write else self._worker,
            self._worker_operation,
            operation,
        )

    async def execute(
        self,
        key: str | Sequence[str] | None,
        operation: Callable[[], _T],
        *,
        operation_name: str | None = None,
        write: bool = True,
    ) -> _T:
        async def run() -> _T:
            return await self.run(operation, write=write)

        return await self.submit(
            key,
            run,
            operation_name=operation_name or getattr(operation, "__name__", "session operation"),
        )

    async def submit(
        self,
        key: str | Sequence[str] | None,
        operation: Callable[[], Awaitable[_T]],
        *,
        operation_name: str,
        barrier: bool = True,
    ) -> _T:
        """Admit bounded work with FIFO key affinity or a global barrier."""
        self._bind_loop()
        name = operation_name
        if key is None:
            keys: tuple[str, ...] = ()
            session_label = "<all>"
        elif isinstance(key, str):
            keys = (key,)
            session_label = key
        else:
            keys = tuple(sorted(set(key)))
            if not keys:
                raise ValueError("session operation requires at least one key")
            session_label = ",".join(keys)
        if self._closed:
            raise RuntimeError(
                f"session state is closed: operation={name} session={session_label!r}"
            )
        if self._admitted >= self._capacity:
            raise SessionOperationQueueFullError(
                f"session operation queue is full: operation={name} "
                f"session={session_label!r} capacity={self._capacity}"
            )

        self._admitted += 1
        if key is None:
            predecessors = tuple(self._pending) if barrier else ()
        else:
            ordered = [self._key_tails[item] for item in keys if item in self._key_tails]
            if self._global_tail is not None:
                ordered.append(self._global_tail)
            predecessors = tuple(dict.fromkeys(ordered))

        async def run() -> _T:
            try:
                if predecessors:
                    await asyncio.gather(
                        *(asyncio.shield(predecessor) for predecessor in predecessors),
                        return_exceptions=True,
                    )
                return await operation()
            finally:
                self._admitted -= 1
                for item in keys:
                    if self._key_tails.get(item) is task:
                        self._key_tails.pop(item, None)
                if self._global_tail is task:
                    self._global_tail = None

        task = asyncio.create_task(run())
        if key is None and barrier:
            self._global_tail = task
        else:
            for item in keys:
                self._key_tails[item] = task
        self._pending.add(task)
        try:
            return await shield_and_drain(task)
        finally:
            self._pending.discard(task)

    async def aclose(self) -> None:
        """Reject new operations and drain accepted work without swallowing caller cancellation."""
        self._bind_loop()
        self._closed = True

        async def close() -> None:
            if self._pending:
                await asyncio.gather(*tuple(self._pending), return_exceptions=True)

            def shutdown() -> None:
                self._worker.shutdown(wait=True)
                self._writer.shutdown(wait=True)
                # All SQL users have exited. Each owner closes only connections
                # created by its own executor threads, never another owner's.
                for connection in self._connections:
                    connection.close()
                self._connections.clear()

            await asyncio.to_thread(shutdown)

        if self._close_task is None:
            self._close_task = asyncio.create_task(close())
        # A timeout may stop waiting for shutdown, but it must not cancel the
        # drain itself. Unlike an admitted mutation, close has no commit result
        # that must delay cancellation of its caller.
        await asyncio.shield(self._close_task)
