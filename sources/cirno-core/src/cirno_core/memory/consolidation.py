"""Coordinate session checkpoint admission, commit, and context pressure."""

from __future__ import annotations

import asyncio
import weakref
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable
from uuid import uuid4

from cirno_core.bus.agent_events import (
    NO_EVENTS,
    CompactionReason,
    ContextCompactionEvent,
    EventSink,
)
from cirno_core.memory.archiver import MemoryArchiver
from cirno_core.memory.store import MemoryStore
from cirno_core.memory.working_state import (
    EvidenceCheckpoint,
)
from cirno_core.providers.contracts import ProviderConversationState
from cirno_core.providers.context_budget import ContextBudget
from cirno_core.session.model import Session
from cirno_core.session.manager import SessionManager
from cirno_core.session.summary import is_summary_checkpoint, session_summary_from_metadata
from cirno_core.utils.token_estimation import estimate_message_tokens, estimate_prompt_tokens_chain
from cirno_core.utils.text import truncate_text_to_tokens
from loguru import logger

if TYPE_CHECKING:
    from cirno_core.utils.llm_runtime import LLMRuntime


class Consolidator:
    """Coordinate session Memory checkpoints through ``MemoryArchiver``."""

    _SAFETY_BUFFER = 1024  # extra headroom for tokenizer estimation drift

    def __init__(
        self,
        store: MemoryStore,
        sessions: SessionManager,
        build_messages: Callable[..., list[dict[str, Any]]],
        get_tool_definitions: Callable[[Session], list[dict[str, Any]]],
        resolve_prompt_context: Callable[[Session], tuple[str | None, Path | None]] | None = None,
    ):
        self.store = store
        self.sessions = sessions
        self._build_messages = build_messages
        self._resolve_prompt_context = resolve_prompt_context
        self._get_tool_definitions = get_tool_definitions
        self.archiver = MemoryArchiver(
            store=store,
            build_messages=build_messages,
            get_tool_definitions=get_tool_definitions,
            resolve_prompt_context=resolve_prompt_context,
        )
        self.on_compaction_saved: Callable[[str], Awaitable[None]] | None = None
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

    def get_lock(self, session_key: str) -> asyncio.Lock:
        """Return the shared consolidation lock for one session."""
        return self._locks.setdefault(session_key, asyncio.Lock())

    async def summarize_transcript(
        self,
        accepted_messages: list[dict[str, Any]],
        previous_summary: str | None,
        *,
        runtime: LLMRuntime,
        session_key: str,
        tools: list[dict[str, Any]],
        provider_state: ProviderConversationState | None = None,
        persist: bool = True,
    ) -> str | None:
        """Summarize the exact transcript prefix already accepted by the model."""
        source_messages = [
            dict(message) for message in accepted_messages if message.get("role") != "system"
        ]
        if not source_messages:
            return None

        max_output_tokens = min(runtime.generation.max_tokens, runtime.compaction_max_tokens)
        input_token_budget = self._input_token_budget(runtime)
        checkpoint_tokens = min(
            max_output_tokens,
            max(1, (input_token_budget - self._SAFETY_BUFFER) // 2),
        )

        metadata = await self.sessions.state.read_metadata(session_key) if persist else None
        summary = await self.archiver.archive(
            source_messages,
            runtime=runtime,
            session_key=session_key,
            history=accepted_messages,
            request_tools=tools,
            previous_summary=previous_summary,
            input_token_budget=input_token_budget,
            fallback_max_tokens=max(1, checkpoint_tokens),
            provider_state=provider_state,
            persist=persist,
            project_id=(metadata or {}).get("metadata", {}).get("project_id"),
        )
        if summary is None:
            return None
        text = truncate_text_to_tokens(summary, max(1, max_output_tokens))
        return EvidenceCheckpoint(text) if isinstance(summary, EvidenceCheckpoint) else text

    async def summarize_provider_compaction(
        self,
        state: ProviderConversationState,
        fallback_messages: list[dict[str, Any]],
        previous_summary: str | None,
        *,
        runtime: LLMRuntime,
        session_key: str,
        tools: list[dict[str, Any]],
        persist: bool = True,
    ) -> str | None:
        """Prompt a native compacted state without replaying its raw history."""
        return await self.summarize_transcript(
            fallback_messages,
            previous_summary,
            runtime=runtime,
            session_key=session_key,
            tools=tools,
            provider_state=state,
            persist=persist,
        )

    @staticmethod
    def _full_replay_history(
        session: Session,
    ) -> list[dict[str, Any]]:
        """Return all messages that can reach the next model prompt."""
        if not session.messages:
            return []
        return session.get_history()

    def estimate_session_prompt_tokens(
        self,
        session: Session,
        *,
        runtime: LLMRuntime,
    ) -> tuple[int, str]:
        """Estimate prompt size from the full replayable session history."""
        history = self._full_replay_history(session)
        channel = session.key.split(":", 1)[0] if ":" in session.key else None
        summary = session_summary_from_metadata(
            session.metadata,
            fallback_last_active=session.updated_at,
        )
        workspace = None
        if self._resolve_prompt_context is not None:
            channel, workspace = self._resolve_prompt_context(session)
        probe_messages = self._build_messages(
            history=history,
            current_message=None,
            channel=channel,
            session_summary=dict(summary) if summary else None,
            session_key=session.key,
            workspace=workspace,
        )
        return estimate_prompt_tokens_chain(
            runtime.provider,
            runtime.model,
            probe_messages,
            self._get_tool_definitions(session),
        )

    def _input_token_budget(self, runtime: LLMRuntime) -> int:
        """Available input token budget for consolidation LLM."""
        return ContextBudget(
            runtime.context_window_tokens,
            min(runtime.generation.max_tokens, runtime.compaction_max_tokens),
            runtime.output_reserve_percent,
        ).input_limit

    async def archive_session(
        self,
        session: Session,
        *,
        archive_end: int,
        runtime: LLMRuntime,
    ) -> str | None:
        """Archive one captured session range through the shared Memory path."""
        return await self.archiver.archive_session(
            session,
            archive_end=archive_end,
            runtime=runtime,
            input_token_budget=self._input_token_budget(runtime),
        )

    async def compact_idle_session(
        self,
        session_key: str,
        *,
        runtime: LLMRuntime,
        events: EventSink = NO_EVENTS,
        notify: bool = False,
        reason: CompactionReason | None = None,
        keep_recent_tokens: int = 0,
    ) -> str | None:
        """Replace archived history with a summary checkpoint.

        All compaction triggers share checkpoint replay.
        """
        lock = self.get_lock(session_key)
        async with lock:
            await self.sessions.state.discard(session_key)
            session = await self.sessions.state.get(session_key)

            archive_start = session.last_archived
            archive_end = self._archive_boundary(session, keep_recent_tokens)
            messages_to_archive = list(session.messages[archive_start:archive_end])
            has_new_messages = any(
                not message.get("_command") and not is_summary_checkpoint(message)
                for message in messages_to_archive
            )
            if not has_new_messages:
                return ""

            compaction_id = uuid4().hex
            await events.emit(
                ContextCompactionEvent(
                    compaction_id=compaction_id, phase="started", notify=notify, reason=reason
                ),
            )
            try:
                summary = await self.archive_session(
                    session,
                    archive_end=archive_end,
                    runtime=runtime,
                )
                if summary:
                    await self.sessions.state.commit_summary(
                        session,
                        summary,
                        archive_end=archive_end,
                    )
            except (Exception, asyncio.CancelledError) as exc:
                await events.emit(
                    ContextCompactionEvent(
                        compaction_id=compaction_id,
                        phase="cancelled" if isinstance(exc, asyncio.CancelledError) else "failed",
                        notify=notify,
                        reason=reason,
                        error=None
                        if isinstance(exc, asyncio.CancelledError)
                        else f"{type(exc).__name__}: {exc}"[:1000],
                    ),
                )
                raise
            if not summary:
                await events.emit(
                    ContextCompactionEvent(
                        compaction_id=compaction_id,
                        phase="failed",
                        notify=notify,
                        reason=reason,
                        error="Archiving produced no summary; context was not changed.",
                    ),
                )
                return None

            compacted_session = await self.sessions.state.get(session_key)
            context_tokens, _ = await asyncio.to_thread(
                self.estimate_session_prompt_tokens,
                compacted_session,
                runtime=runtime,
            )
            await events.emit(
                ContextCompactionEvent(
                    compaction_id=compaction_id,
                    phase="succeeded",
                    notify=notify,
                    reason=reason,
                    context_tokens=context_tokens,
                    context_window_tokens=runtime.context_window_tokens,
                    context_estimated=True,
                    evidence_checkpoint=isinstance(summary, EvidenceCheckpoint),
                ),
            )

            logger.info(
                "Idle-session compact for {}: archived={}, visible={}, retained={}, summary={}",
                session_key,
                len(messages_to_archive),
                len(session.get_history()),
                len(session.messages),
                bool(summary),
            )

            if self.on_compaction_saved:
                await self.on_compaction_saved(session_key)
            return summary

    @staticmethod
    def _archive_boundary(session: Session, keep_recent_tokens: int) -> int:
        """Keep complete recent user turns within the requested token budget."""
        end = len(session.messages)
        if keep_recent_tokens <= 0:
            return end
        tokens = 0
        boundary = end
        for index in range(end - 1, session.last_archived - 1, -1):
            message = session.messages[index]
            tokens += estimate_message_tokens(message)
            if tokens > keep_recent_tokens:
                break
            if (
                message.get("role") == "user"
                and not message.get("_command")
                and not is_summary_checkpoint(message)
            ):
                boundary = index
        return boundary
