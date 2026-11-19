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
from cirno_core.utils.cancellation import shield_and_drain


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

    try:
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
            if poll.output or poll.output_gaps:
                aggregate.append(poll.output, gaps=poll.output_gaps)
                if wait_for is not None:
                    overlap_chars = len(wait_for) - 1
                    start = 0
                    # A retained head and tail are not adjacent in the real
                    # stream. Only carry a suffix across contiguous pieces.
                    for index, boundary in enumerate((*poll.output_gaps, len(poll.output))):
                        if index:
                            search_overlap = ""
                        searchable = search_overlap + poll.output[start:boundary]
                        matched = wait_for in searchable
                        if matched:
                            break
                        search_overlap = searchable[-overlap_chars:] if overlap_chars else ""
                        start = boundary

            expired = time.monotonic() >= deadline
            has_activity = wait_for is None and not until_exit and bool(poll.output)
            if poll.done or matched or has_activity or expired:
                poll.stdin_closed = stdin_was_closed
                poll.output, aggregate_truncated, poll.output_gaps = aggregate.drain_with_gaps()
                poll.truncated_chars = upstream_truncated + aggregate_truncated
                return SessionObservation(poll=poll, matched=matched, expired=expired)
    except BaseException:
        # Polling consumes the session buffer. A cancelled/failed multi-poll
        # wait must not discard logs that never reached its caller.
        output, dropped, gaps = aggregate.drain_with_gaps()
        if output or upstream_truncated or dropped:
            await shield_and_drain(manager.return_output(
                session_id=session_id, output=output,
                truncated_chars=upstream_truncated + dropped,
                owner_session_key=owner_session_key,
                output_gaps=gaps,
            ))
        raise
