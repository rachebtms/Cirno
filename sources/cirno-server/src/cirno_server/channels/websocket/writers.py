"""Bounded, ordered physical writes and retirement for WebSocket connections."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING
from weakref import WeakSet

from websockets.asyncio.server import ServerConnection
from websockets.exceptions import ConnectionClosed

if TYPE_CHECKING:
    from loguru import Logger

_OUTBOUND_QUEUE_MAX_FRAMES = 256

_OUTBOUND_QUEUE_MAX_BYTES = 8 * 1024 * 1024

_OUTBOUND_SEND_TIMEOUT_S = 10.0

_OUTBOUND_CLOSE_TIMEOUT_S = 1.0


@dataclass(slots=True)
class _OutboundFrame:
    raw: str
    utf8_bytes: int
    label: str


@dataclass(slots=True)
class _ConnectionOutbound:
    queue: asyncio.Queue[_OutboundFrame]
    buffered_bytes: int = 0
    writer: asyncio.Task[None] | None = None
    closing: bool = False


class ConnectionWriters:
    def __init__(
        self,
        cleanup: Callable[[ServerConnection], Awaitable[None]],
        logger: Logger,
    ) -> None:
        self.cleanup = cleanup
        self.logger = logger
        self.states: dict[ServerConnection, _ConnectionOutbound] = {}
        self.retire_tasks: set[asyncio.Task[None]] = set()
        self.retired: WeakSet[ServerConnection] = WeakSet()

    @property
    def connections(self) -> tuple[ServerConnection, ...]:
        return tuple(self.states)

    def accept(self, connection: ServerConnection) -> None:
        """Begin a transport lifetime; registration waits for its ready frame."""
        self.retired.discard(connection)

    async def begin_cleanup(self, connection: ServerConnection) -> _ConnectionOutbound | None:
        self.retired.add(connection)
        state = self.states.get(connection)
        if state is not None:
            state.closing = True
            await self._stop_writer(state)
        return state

    def finish_cleanup(
        self, connection: ServerConnection, state: _ConnectionOutbound | None
    ) -> None:
        if self.states.get(connection) is state:
            self.states.pop(connection, None)

    async def drain_retirements(self) -> None:
        pending = tuple(self.retire_tasks)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def register(self, connection: ServerConnection) -> bool:
        if connection in self.retired:
            return False
        self.states.setdefault(
            connection,
            _ConnectionOutbound(asyncio.Queue(maxsize=_OUTBOUND_QUEUE_MAX_FRAMES)),
        )
        return True

    @staticmethod
    async def _stop_writer(state: _ConnectionOutbound) -> None:
        task = state.writer
        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        while True:
            try:
                state.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        state.buffered_bytes = 0

    def _start_writer(
        self,
        connection: ServerConnection,
        state: _ConnectionOutbound,
    ) -> None:
        if state.closing or (state.writer is not None and not state.writer.done()):
            return
        state.writer = asyncio.create_task(
            self._drain(connection, state),
            name=f"websocket-outbound-{id(connection):x}",
        )

    @property
    def has_pending(self) -> bool:
        # send() only enqueues a frame. buffered_bytes includes the frame that
        # a writer has removed from its queue but has not finished transmitting.
        return bool(self.retire_tasks) or any(
            state.buffered_bytes
            or not state.queue.empty()
            or (state.writer is not None and not state.writer.done())
            for state in self.states.values()
        )

    async def _drain(
        self,
        connection: ServerConnection,
        state: _ConnectionOutbound,
    ) -> None:
        current = asyncio.current_task()
        try:
            while not state.closing:
                try:
                    frame = state.queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    async with asyncio.timeout(_OUTBOUND_SEND_TIMEOUT_S):
                        await connection.send(frame.raw)
                except asyncio.CancelledError:
                    raise
                except TimeoutError:
                    self.logger.warning("connection send timed out{}", frame.label)
                    self._schedule_retirement(
                        connection,
                        state,
                        close_connection=True,
                        close_code=1013,
                        close_reason="outbound send timeout",
                    )
                    return
                except ConnectionClosed:
                    self.logger.warning("connection gone{}", frame.label)
                    self._schedule_retirement(
                        connection,
                        state,
                        close_connection=False,
                    )
                    return
                except Exception:
                    self.logger.exception("send failed{}", frame.label)
                    self._schedule_retirement(
                        connection,
                        state,
                        close_connection=True,
                        close_code=1011,
                        close_reason="outbound send failed",
                    )
                    return
                finally:
                    state.buffered_bytes = max(0, state.buffered_bytes - frame.utf8_bytes)
        finally:
            if state.writer is current:
                state.writer = None
            if not state.closing and not state.queue.empty():
                self._start_writer(connection, state)

    def _schedule_retirement(
        self,
        connection: ServerConnection,
        state: _ConnectionOutbound,
        *,
        close_connection: bool,
        close_code: int = 1000,
        close_reason: str = "",
    ) -> None:
        if state.closing:
            return
        state.closing = True
        task = asyncio.create_task(
            self._retire(
                connection,
                close_connection=close_connection,
                close_code=close_code,
                close_reason=close_reason,
            ),
            name=f"websocket-retire-{id(connection):x}",
        )
        self.retire_tasks.add(task)
        task.add_done_callback(self.retire_tasks.discard)

    async def _retire(
        self,
        connection: ServerConnection,
        *,
        close_connection: bool,
        close_code: int,
        close_reason: str,
    ) -> None:
        try:
            if close_connection:
                try:
                    async with asyncio.timeout(_OUTBOUND_CLOSE_TIMEOUT_S):
                        await connection.close(code=close_code, reason=close_reason)
                except TimeoutError:
                    self.logger.warning("timed out closing slow WebSocket connection")
                    with suppress(Exception):
                        connection.transport.abort()
                except ConnectionClosed:
                    pass
                except Exception:
                    self.logger.exception("failed to close WebSocket connection")
                    with suppress(Exception):
                        connection.transport.abort()
        finally:
            try:
                await self.cleanup(connection)
            except Exception:
                self.logger.exception("failed to clean up WebSocket connection")

    async def send(
        self,
        connection: ServerConnection,
        raw: str,
        *,
        label: str = "",
    ) -> None:
        """Queue one frame without letting this connection block other clients."""
        state = self.states.get(connection)
        if state is None or state.closing:
            return
        utf8_bytes = len(raw.encode("utf-8"))
        if state.queue.full() or state.buffered_bytes + utf8_bytes > _OUTBOUND_QUEUE_MAX_BYTES:
            self.logger.warning(
                "disconnecting slow WebSocket connection: outbound queue full "
                "({} frames, {} bytes)",
                state.queue.qsize(),
                state.buffered_bytes,
            )
            self._schedule_retirement(
                connection,
                state,
                close_connection=True,
                close_code=1013,
                close_reason="outbound queue full",
            )
            await asyncio.sleep(0)
            return
        state.queue.put_nowait(_OutboundFrame(raw, utf8_bytes, label))
        state.buffered_bytes += utf8_bytes
        self._start_writer(connection, state)
        # Give an idle writer a chance to start without waiting for physical I/O.
        await asyncio.sleep(0)
