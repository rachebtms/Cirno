"""Per-runtime process admission, owner routing and retained results."""

from __future__ import annotations

import asyncio
import shlex
import time
import uuid
from typing import Literal

from cirno_core.processes import launch as process_launch
from cirno_core.processes.sessions.contracts import ExecSessionInfo, FinishReason, SessionPoll
from cirno_core.processes.sessions.session import ExecSession


class ExecSessionManager:
    def __init__(self, *, max_sessions: int = 8, result_retention: int = 1800) -> None:
        self.max_sessions = max_sessions
        self.result_retention = result_retention
        self._sessions: dict[str, ExecSession] = {}
        self._starting: dict[str, tuple[str | None, asyncio.Task[ExecSession]]] = {}
        self._stopping_launches: set[asyncio.Task[ExecSession]] = set()
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def has_pending_work(self) -> bool:
        """Inspect owned work without polling, terminating or removing sessions."""
        return bool(
            self._lock.locked()
            or self._starting
            or self._stopping_launches
            or any(s.has_pending_work for s in self._sessions.values())
        )

    async def start(
        self,
        *,
        command: str | list[str],
        cwd: str,
        env: dict[str, str],
        timeout: int | None,
        shell_program: str | None,
        login: bool,
        yield_time_ms: int,
        max_output_chars: int,
        owner_session_key: str | None = None,
        idle_timeout: int = 300,
        idle_action: Literal["report", "terminate"] = "report",
        stdin: int = asyncio.subprocess.PIPE,
        until_exit: bool = False,
        log_content: bool = True,
    ) -> tuple[str, SessionPoll]:
        async with self._lock:
            if self._closed:
                raise RuntimeError("exec session manager is closed")
            self._cleanup_finished_locked()
            if len(self._sessions) + len(self._starting) >= self.max_sessions:
                finished = [
                    (session.finished_at, session_id)
                    for session_id, session in self._sessions.items()
                    if session.finished_at is not None
                ]
                if not finished:
                    raise RuntimeError(f"maximum exec sessions reached ({self.max_sessions})")
                self._sessions.pop(min(finished)[1])
            session_id = uuid.uuid4().hex[:12]
            launch = asyncio.create_task(
                self._launch(
                    session_id=session_id,
                    command=command,
                    cwd=cwd,
                    env=env,
                    timeout=timeout,
                    shell_program=shell_program,
                    login=login,
                    owner_session_key=owner_session_key,
                    idle_timeout=idle_timeout,
                    idle_action=idle_action,
                    stdin=stdin,
                    log_content=log_content,
                )
            )
            self._starting[session_id] = (owner_session_key, launch)
        try:
            session = await launch
            if until_exit:
                await session.wait_exit()
            poll = await session.poll(yield_time_ms, max_output_chars)
        except asyncio.CancelledError:
            if launch.done() and not launch.cancelled() and launch.exception() is None:
                await launch.result().kill("cancelled")
                async with self._lock:
                    self._sessions.pop(session_id, None)
            raise
        finally:
            async with self._lock:
                self._starting.pop(session_id, None)
        if poll.done:
            async with self._lock:
                self._sessions.pop(session_id, None)
        return session_id, poll

    async def _launch(
        self,
        *,
        session_id: str,
        command: str | list[str],
        cwd: str,
        env: dict[str, str],
        timeout: int | None,
        shell_program: str | None,
        login: bool,
        owner_session_key: str | None,
        idle_timeout: int,
        idle_action: Literal["report", "terminate"],
        stdin: int,
        log_content: bool,
    ) -> ExecSession:
        session: ExecSession | None = None
        try:
            started_at = time.monotonic()
            process = await self._spawn(command, cwd, env, shell_program, login, stdin=stdin)
            session = ExecSession(
                session_id=session_id,
                process=process,
                command=shlex.join(command) if isinstance(command, list) else command,
                cwd=cwd,
                timeout=timeout,
                owner_session_key=owner_session_key,
                process_tree=True,
                idle_timeout=idle_timeout,
                idle_action=idle_action,
                started_at=started_at,
                log_content=log_content,
            )
            async with self._lock:
                if self._closed or session_id not in self._starting:
                    raise RuntimeError("exec session owner closed during startup")
                self._sessions[session_id] = session
            return session
        except BaseException:
            if session is not None:
                try:
                    await session.kill("owner_closed")
                except BaseException:
                    async with self._lock:
                        self._sessions[session_id] = session
                    raise
            raise
        finally:
            async with self._lock:
                self._starting.pop(session_id, None)

    async def write(
        self,
        *,
        session_id: str,
        chars: str | None,
        close_stdin: bool,
        terminate: bool,
        yield_time_ms: int,
        max_output_chars: int,
        owner_session_key: str | None = None,
    ) -> SessionPoll:
        async with self._lock:
            self._cleanup_finished_locked()
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        if session.owner_session_key and session.owner_session_key != owner_session_key:
            raise KeyError(session_id)

        if chars:
            error = await session.write(chars)
            if error:
                raise RuntimeError(error)
        stdin_closed = False
        if close_stdin:
            error = await session.close_stdin()
            if error:
                raise RuntimeError(error)
            stdin_closed = True
        if terminate:
            await session.kill()
        poll = await session.poll(
            yield_time_ms,
            max_output_chars,
            stdin_closed=stdin_closed,
        )
        if poll.done:
            async with self._lock:
                self._sessions.pop(session_id, None)
        return poll

    async def list(self, *, owner_session_key: str | None = None) -> list[ExecSessionInfo]:
        async with self._lock:
            self._cleanup_finished_locked()
            now = time.monotonic()
            return [
                ExecSessionInfo(
                    session_id=session_id,
                    command=session.command,
                    cwd=session.cwd,
                    elapsed_s=max(0.0, now - session.started_at),
                    idle_s=session.output_idle_s(now),
                    remaining_s=session.remaining_s(now),
                    returncode=session.process.returncode,
                    owner_session_key=session.owner_session_key,
                    idle_timeout=session.idle_timeout,
                    stopping=session.stopping,
                    finish_reason=session.finish_reason,
                    cleanup_error=session.cleanup_error,
                )
                for session_id, session in sorted(self._sessions.items())
                if session.owner_session_key == owner_session_key
            ]

    async def close_all(self) -> int:
        """Terminate and remove all active sessions during shutdown."""
        async with self._lock:
            self._closed = True
            sessions: list[ExecSession] = list(self._sessions.values())
            launches = [task for _, task in self._starting.values()]
            self._starting.clear()
        return await self._stop_owned(sessions, launches, "shutdown")

    async def terminate_by_owner(self, owner_session_key: str) -> int:
        """Terminate all sessions owned by owner_session_key. Returns count."""
        async with self._lock:
            victims: list[ExecSession] = []
            for s in self._sessions.values():
                if s.owner_session_key == owner_session_key:
                    victims.append(s)
            launches = [
                task for owner, task in self._starting.values() if owner == owner_session_key
            ]
            for sid, (owner, _) in list(self._starting.items()):
                if owner == owner_session_key:
                    self._starting.pop(sid)
        return await self._stop_owned(victims, launches, "owner_closed")

    async def _stop_owned(
        self,
        sessions: list[ExecSession],
        launches: list[asyncio.Task[ExecSession]],
        reason: FinishReason,
    ) -> int:
        # Removed startup reservations must stay visible until cancellation drains.
        self._stopping_launches.update(launches)
        for task in launches:
            task.add_done_callback(self._stopping_launches.discard)
        results: list[None | BaseException] = list(
            await asyncio.gather(
                *(session.kill(reason) for session in sessions),
                self._cancel_launches(launches),
                return_exceptions=True,
            )
        )
        startup_error = results.pop()
        failures = [
            (session, result)
            for session, result in zip(sessions, results, strict=True)
            if isinstance(result, BaseException)
        ]
        async with self._lock:
            for session, result in zip(sessions, results, strict=True):
                if not isinstance(result, BaseException):
                    self._sessions.pop(session.session_id, None)
        errors = [result for _, result in failures]
        if isinstance(startup_error, BaseException):
            errors.append(startup_error)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise BaseExceptionGroup("failed to stop owned exec sessions", errors)
        return len(sessions) + len(launches)

    @staticmethod
    async def _cancel_launches(launches: list[asyncio.Task[ExecSession]]) -> None:
        for task in launches:
            task.cancel()
        results = await asyncio.gather(*launches, return_exceptions=True)
        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            raise ExceptionGroup("failed to cancel exec startup", errors)

    def _cleanup_finished_locked(self) -> None:
        now = time.monotonic()
        stale = [
            session_id
            for session_id, session in self._sessions.items()
            if session.finished_at is not None and now - session.finished_at > self.result_retention
        ]
        for session_id in stale:
            self._sessions.pop(session_id)

    async def _spawn(
        self,
        command: str | list[str],
        cwd: str,
        env: dict[str, str],
        shell_program: str | None,
        login: bool,
        *,
        stdin: int = asyncio.subprocess.PIPE,
    ) -> asyncio.subprocess.Process:
        return await process_launch.spawn_process(
            command,
            cwd,
            env,
            shell_program,
            login,
            stdin=stdin,
            process_tree=True,
        )
