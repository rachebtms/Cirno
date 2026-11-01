"""Auto compact: proactive compression of idle sessions to reduce token cost and latency."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Collection
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from cirno.bus.agent_events import NO_EVENTS, EventSink
from cirno.session.keys import is_dream_session
from cirno.session.manager import Session, SessionManager
from cirno.session.summary import (
    SessionSummary,
    session_summary_from_metadata,
)
from loguru import logger

if TYPE_CHECKING:
    from cirno.memory.consolidation import Consolidator
    from cirno.utils.llm_runtime import LLMRuntime

SessionEventFactory = Callable[[str], EventSink]


class AutoCompact:
    def __init__(
        self,
        sessions: SessionManager,
        consolidator: Consolidator,
        session_ttl_minutes: int = 0,
        bind_events: SessionEventFactory | None = None,
        *,
        session_lock: Callable[[str], asyncio.Lock],
        trigger_percent: float | None = None,
        keep_percent: float | None = None,
        min_context_tokens: int = 0,
        keep_recent_tokens: int = 0,
    ):
        self.sessions = sessions
        self.consolidator = consolidator
        self._ttl = session_ttl_minutes
        self._archiving: set[str] = set()
        self._summaries: dict[str, SessionSummary] = {}
        self._bind_events = bind_events
        self._session_lock = session_lock
        self._trigger_percent = trigger_percent
        self._keep_percent = keep_percent
        self._min_context_tokens = min_context_tokens
        self._keep_recent_tokens = keep_recent_tokens

    def _is_expired(self, ts: datetime | str | None,
                    now: datetime | None = None) -> bool:
        if self._ttl <= 0 or not ts:
            return False
        try:
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            current = now or datetime.now()
            if getattr(ts, "tzinfo", None) is not None or current.tzinfo is not None:
                idle_seconds = current.timestamp() - ts.timestamp()
            else:
                idle_seconds = (current - ts).total_seconds()
        except (OSError, OverflowError, TypeError, ValueError):
            # list_sessions() forwards raw persisted metadata; an unusable value
            # must not escape the idle scan and stop the agent loop.
            return False
        return idle_seconds >= self._ttl * 60

    async def check_expired(
        self,
        schedule_background: Callable[[Coroutine[Any, Any, None]], None],
        resolve_runtime: Callable[[Session], Awaitable[LLMRuntime]],
        active_session_keys: Collection[str] = (),
    ) -> None:
        """Schedule idle archival without blocking the event loop."""
        now = datetime.now()
        active_keys = set(active_session_keys)
        for info in await self.sessions.state.list_sessions():
            key = info.get("key", "")
            if (
                not key
                or is_dream_session(key)
                or key.startswith("subagent:")
                or key in self._archiving
            ):
                continue
            if key in active_keys or not self._is_expired(info.get("updated_at"), now):
                continue
            if not await self.sessions.state.has_unarchived_messages(key):
                continue
            session = await self.sessions.state.get(key)
            try:
                runtime = await resolve_runtime(session)
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping idle compaction for {}: {}", key, exc)
                continue
            self._archiving.add(key)
            schedule_background(self._archive(key, runtime=runtime))

    async def _archive(self, key: str, *, runtime: LLMRuntime) -> None:
        if is_dream_session(key):
            self._archiving.discard(key)
            return
        try:
            async with self._session_lock(key):
                # A turn may have refreshed activity while this archive waited.
                session = await self.sessions.state.get_header(key)
                if not self._is_expired(session.updated_at):
                    return
                trigger = runtime.idle_compact_percent if isinstance(runtime.idle_compact_percent, (int, float)) else self._trigger_percent
                keep = runtime.idle_compact_keep_percent if isinstance(runtime.idle_compact_keep_percent, (int, float)) else self._keep_percent
                if trigger == 0:
                    return
                minimum = int(runtime.context_window_tokens * trigger / 100) if trigger is not None else self._min_context_tokens
                retention = int(runtime.context_window_tokens * keep / 100) if keep is not None else self._keep_recent_tokens
                if trigger and keep is not None and keep >= trigger:
                    raise ValueError("Recent-context retention must be below the compaction trigger percentage")
                if minimum > 0:
                    session = await self.sessions.state.get(key)
                    tokens, _ = await asyncio.to_thread(
                        self.consolidator.estimate_session_prompt_tokens,
                        session, runtime=runtime,
                    )
                    if tokens < minimum:
                        return
                # Idle compaction and turns share one transcript boundary.
                summary = await self.consolidator.compact_idle_session(
                    key,
                    runtime=runtime,
                    events=self._bind_events(key) if self._bind_events else NO_EVENTS,
                    reason="idle",
                    keep_recent_tokens=retention,
                )
                if summary:
                    session = await self.sessions.state.get(key)
                    stored = session_summary_from_metadata(
                        session.metadata,
                        fallback_last_active=session.updated_at,
                    )
                    if stored is not None:
                        self._summaries[key] = stored
        except Exception:
            logger.exception("Auto-compact: failed for {}", key)
        finally:
            self._archiving.discard(key)

    async def prepare_session(
        self,
        session: Session,
        key: str,
    ) -> tuple[Session, SessionSummary | None]:
        """Resolve a summary while preserving the turn's owner-issued draft."""
        if is_dream_session(key):
            self._archiving.discard(key)
            self._summaries.pop(key, None)
            return session, None
        # Hot path: summary from in-memory dict (process hasn't restarted).
        entry = self._summaries.pop(key, None)
        if entry:
            return session, entry
        # Cold path: summary persisted in session metadata (process restarted).
        # Persisted metadata may outlive schema changes; a malformed summary must
        # not abort turn preparation.
        return session, session_summary_from_metadata(
            session.metadata,
            fallback_last_active=session.updated_at,
        )
