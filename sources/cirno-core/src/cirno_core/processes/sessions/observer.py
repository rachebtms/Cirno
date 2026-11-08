"""Observe bounded process output without terminating the running session."""

from __future__ import annotations

import time
from dataclasses import dataclass

from cirno_core.processes.sessions.buffer import BoundedOutputBuffer
from cirno_core.processes.sessions.contracts import (
    DEFAULT_MAX_OUTPUT_CHARS,
    MAX_OUTPUT_CHARS,
    MAX_YIELD_MS,
    SessionPoll,
)
from cirno_core.processes.sessions.manager import ExecSessionManager


@dataclass(slots=True)
class SessionObservation:
    poll: SessionPoll
    matched: bool
    expired: bool


async def observe_session(
    manager: ExecSessionManager,
    *,
    session_id: str,
    input: str | None,
    close_stdin: bool,
    wait_for: str | None,
    until_exit: bool,
    timeout_ms: int,
    owner_session_key: str | None = None,
) -> SessionObservation:
    deadline = time.monotonic() + (timeout_ms / 1000)
    aggregate = BoundedOutputBuffer(DEFAULT_MAX_OUTPUT_CHARS)
    upstream_truncated = 0
    search_overlap = ""
    first = True
    matched = False
    stdin_was_closed = False

    while True:
        remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
        step_ms = min(MAX_YIELD_MS if until_exit else 500, remaining_ms)
        poll = await manager.write(
            session_id=session_id,
            chars=input if first else None,
            close_stdin=close_stdin if first else False,
            terminate=False,
            yield_time_ms=step_ms,
            max_output_chars=MAX_OUTPUT_CHARS,
            owner_session_key=owner_session_key,
        )
        first = False
        stdin_was_closed = stdin_was_closed or poll.stdin_closed
        upstream_truncated += poll.truncated_chars
        if poll.output:
            aggregate.append(poll.output)
            if wait_for is not None:
                searchable = search_overlap + poll.output
                matched = wait_for in searchable
                overlap_chars = len(wait_for) - 1
                search_overlap = searchable[-overlap_chars:] if overlap_chars else ""

        expired = time.monotonic() >= deadline
        has_activity = wait_for is None and not until_exit and bool(poll.output)
        if poll.done or matched or has_activity or expired:
            poll.stdin_closed = stdin_was_closed
            poll.output, aggregate_truncated = aggregate.drain()
            poll.truncated_chars = upstream_truncated + aggregate_truncated
            return SessionObservation(poll=poll, matched=matched, expired=expired)
