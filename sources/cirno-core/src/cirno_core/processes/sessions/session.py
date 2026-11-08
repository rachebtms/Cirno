"""Supervise a process, its output streams and cancellation lifetime."""

from __future__ import annotations

import asyncio
import codecs
import time
from contextlib import suppress
from typing import Literal

from cirno_core.processes import lifecycle as process_lifecycle
from cirno_core.processes.output import ShellOutputFilter
from cirno_core.processes.sessions.buffer import BoundedOutputBuffer, truncate_output
from cirno_core.processes.sessions.contracts import (
    MAX_OUTPUT_CHARS,
    MAX_YIELD_MS,
    FinishReason,
    SessionPoll,
)
from loguru import logger


class ExecSession:
    def __init__(
        self,
        *,
        session_id: str,
        process: asyncio.subprocess.Process,
        command: str,
        cwd: str,
        timeout: int | None,
        owner_session_key: str | None = None,
        process_tree: bool = False,
        idle_timeout: int = 300,
        idle_action: Literal["report", "terminate"] = "report",
        started_at: float | None = None,
        log_content: bool = True,
    ) -> None:
        self.log_content = log_content
        self.session_id = session_id
        self.process = process
        self.command = command
        self.cwd = cwd
        self.owner_session_key = owner_session_key
        self._process_tree = process_tree
        self.started_at = time.monotonic() if started_at is None else started_at
        self.deadline = self.started_at + timeout if timeout else float("inf")
        self.last_output_at: float | None = None
        self.finished_at: float | None = None
        self._execution_exited = False
        self.idle_timeout = idle_timeout
        self.idle_action = idle_action
        self.finish_reason: FinishReason | None = None
        self._stop_reason: FinishReason | None = None
        self.cleanup_error: str | None = None
        self._stop_complete = asyncio.Event()
        self._state_changed = asyncio.Event()
        self._output_incomplete = False
        self._execution_error: str | None = None
        self._stdout = BoundedOutputBuffer(MAX_OUTPUT_CHARS)
        self._stderr = BoundedOutputBuffer(MAX_OUTPUT_CHARS)
        self._lock = asyncio.Lock()
        self._kill_task: asyncio.Task[None] | None = None
        self._stdout_task = asyncio.create_task(self._read_stream(process.stdout, self._stdout))
        self._stderr_task = asyncio.create_task(self._read_stream(process.stderr, self._stderr))
        self._completion_task = asyncio.create_task(self._complete())
        self._completion_task.add_done_callback(self._on_supervisor_done)
        self._timeout_task = (
            asyncio.create_task(self._watch_timeout())
            if timeout or (idle_timeout and idle_action == "terminate")
            else None
        )
        if self._timeout_task is not None:
            self._timeout_task.add_done_callback(self._on_supervisor_done)

    @property
    def stopping(self) -> bool:
        return self._stop_reason is not None and self.finished_at is None

    def output_idle_s(self, now: float) -> float:
        anchor = self.started_at if self.last_output_at is None else self.last_output_at
        return max(0.0, now - anchor)

    def remaining_s(self, now: float) -> float | None:
        return max(0.0, self.deadline - now) if self.deadline != float("inf") else None

    def _on_supervisor_done(self, task: asyncio.Task[None]) -> None:
        if not task.cancelled() and (error := task.exception()) is not None:
            if task is self._completion_task:
                self.cleanup_error = str(error)
                self._state_changed.set()
            logger.opt(exception=error if self.log_content else False).error(
                "Exec session supervision failed for {}",
                self.session_id,
            )

    async def _complete(self) -> None:
        await self.process.wait()
        # Root exit is not completion while a worker still holds captured pipes.
        readers = asyncio.gather(self._stdout_task, self._stderr_task)
        stopped = asyncio.create_task(self._stop_complete.wait())
        try:
            await asyncio.wait({readers, stopped}, return_when=asyncio.FIRST_COMPLETED)
            if stopped.done():
                try:
                    await asyncio.wait_for(readers, timeout=2.0)
                except asyncio.TimeoutError:
                    self._output_incomplete = True
            else:
                await readers
            self._execution_exited = True
            if self._stop_reason is not None:
                await stopped
        finally:
            stopped.cancel()
            await asyncio.gather(stopped, return_exceptions=True)
        process_lifecycle.release_process_tree(self.process)
        process_lifecycle.reap_pid(self.process.pid)
        self.finish_reason = self._stop_reason or "exit"
        self.finished_at = time.monotonic()
        self._state_changed.set()

    async def wait_exit(self) -> None:
        while self.finished_at is None:
            if self.cleanup_error is not None:
                raise RuntimeError(
                    f"session {self.session_id} cleanup failed: {self.cleanup_error}"
                )
            self._state_changed.clear()
            await self._state_changed.wait()

    @property
    def has_pending_work(self) -> bool:
        """Include pipe draining and failed/in-flight process-tree cleanup."""
        cleanup = self._kill_task
        return (
            self.finished_at is None
            or not self._stdout_task.done()
            or not self._stderr_task.done()
            or (
                cleanup is not None
                and (not cleanup.done() or cleanup.cancelled() or cleanup.exception() is not None)
            )
        )

    async def _watch_timeout(self) -> None:
        """Supervise execution budgets independently of tool waits and log reads."""
        while not self._completion_task.done():
            now = time.monotonic()
            deadline = self.deadline
            if self.idle_timeout and self.idle_action == "terminate":
                anchor = self.started_at if self.last_output_at is None else self.last_output_at
                deadline = min(deadline, anchor + self.idle_timeout)
            done, _ = await asyncio.wait(
                {self._completion_task},
                timeout=max(0.0, deadline - now),
            )
            if done:
                return
            if self._execution_exited:
                await asyncio.shield(self._completion_task)
                return
            now = time.monotonic()
            if now >= self.deadline:
                await self.kill("max_runtime")
                return
            if self.idle_timeout and self.idle_action == "terminate":
                if self.output_idle_s(now) >= self.idle_timeout:
                    await self.kill("idle_timeout")
                    return

    async def _read_stream(
        self,
        stream: asyncio.StreamReader | None,
        buffer: BoundedOutputBuffer,
    ) -> None:
        if stream is None:
            return
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        output_filter = ShellOutputFilter()
        try:
            while True:
                chunk = await stream.read(4096)
                if chunk:
                    self.last_output_at = time.monotonic()
                text = output_filter.feed(decoder.decode(chunk, final=not chunk))
                async with self._lock:
                    buffer.append(text)
                if not chunk:
                    break
        except Exception as exc:
            self._output_incomplete = True
            self._execution_error = str(exc)
            await self._begin_stop("execution_error")

    async def write(self, chars: str) -> str | None:
        if self.process.returncode is not None:
            return "session has already exited"
        if self.process.stdin is None:
            return "session stdin is not available"
        try:
            self.process.stdin.write(chars.encode("utf-8"))
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            return "session stdin is closed"
        return None

    async def close_stdin(self) -> str | None:
        if self.process.returncode is not None:
            return "session has already exited"
        if self.process.stdin is None:
            return "session stdin is not available"
        self.process.stdin.close()
        with suppress(BrokenPipeError, ConnectionResetError):
            await self.process.stdin.wait_closed()
        return None

    async def poll(
        self,
        yield_time_ms: int,
        max_output_chars: int,
        *,
        stdin_closed: bool = False,
    ) -> SessionPoll:
        if yield_time_ms > 0 and not self._completion_task.done():
            await asyncio.wait(
                {self._completion_task},
                timeout=min(yield_time_ms, MAX_YIELD_MS) / 1000,
            )
        if self._completion_task.done():
            await asyncio.shield(self._completion_task)
        if self.cleanup_error is not None:
            raise RuntimeError(f"session {self.session_id} cleanup failed: {self.cleanup_error}")

        async with self._lock:
            stdout, stdout_truncated = self._stdout.drain()
            stderr, stderr_truncated = self._stderr.drain()

        output_parts = [stdout] if stdout else []
        if stderr:
            output_parts.append(f"STDERR:\n{stderr}")
        output = "\n".join(output_parts)
        output, response_truncated = truncate_output(output, max_output_chars)
        now = time.monotonic()
        return SessionPoll(
            output=output,
            done=self.finished_at is not None,
            exit_code=self.process.returncode,
            elapsed_s=max(0.0, (self.finished_at or now) - self.started_at),
            finish_reason=self.finish_reason,
            stopping=self.stopping,
            output_idle_s=self.output_idle_s(now),
            idle_timeout=self.idle_timeout,
            remaining_s=self.remaining_s(now),
            stdin_closed=stdin_closed,
            truncated_chars=stdout_truncated + stderr_truncated + response_truncated,
            output_incomplete=self._output_incomplete,
            execution_error=self._execution_error,
        )

    async def kill(self, reason: FinishReason = "cancelled") -> None:
        await self._begin_stop(reason)
        await asyncio.shield(self._completion_task)

    async def _begin_stop(self, reason: FinishReason) -> None:
        if not self.has_pending_work:
            return
        if self._execution_exited and self._stop_reason is None:
            return
        if self._stop_reason is None:
            self._stop_reason = reason
        if self._kill_task is None or (
            self._kill_task.done()
            and (self._kill_task.cancelled() or self._kill_task.exception() is not None)
        ):
            self.cleanup_error = None
            self._kill_task = asyncio.create_task(self._kill())
            self._kill_task.add_done_callback(self._on_kill_done)
        await asyncio.shield(self._kill_task)

    def _on_kill_done(self, task: asyncio.Task[None]) -> None:
        error = None if task.cancelled() else task.exception()
        if error is not None:
            self.cleanup_error = str(error)
            self._state_changed.set()
            logger.opt(exception=error if self.log_content else False).error(
                "Failed to terminate exec session {}",
                self.session_id,
            )
        # Retain failed cleanup as unsettled work, even if the parent exited.
        # kill() replaces it on an explicit retry.

    async def _kill(self) -> None:
        if self._process_tree:
            await process_lifecycle.kill_process_tree(self.process)
        else:
            await process_lifecycle.kill_process(self.process)
        self._stop_complete.set()
