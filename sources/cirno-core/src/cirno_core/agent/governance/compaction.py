"""Validate replacement checkpoints before committing model context."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any
from uuid import uuid4

from cirno_core.agent.governance import budget
from cirno_core.agent.governance.budget import fit_pending_file_reads, input_budget
from cirno_core.agent.governance.contracts import ContextWindowExceededError, ModelRequestState
from cirno_core.agent.governance.messages import prepare_messages
from cirno_core.agent.governance.preparation import PromptPreparation
from cirno_core.agent.governance.state import ContextCompactionState
from cirno_core.bus.agent_events import ContextCompactionEvent
from cirno_core.memory.working_state import EvidenceCheckpoint
from cirno_core.providers.contracts import (
    LLMResponse,
)
from cirno_core.session.history_visibility import is_hidden_history_message
from cirno_core.session.summary import (
    SUMMARY_CONTINUATION_TEXT,
    SessionSummaryCheckpoint,
)
from cirno_core.utils.cancellation import shield_and_drain
from loguru import logger


def _summary_transcript(
    compaction: ContextCompactionState,
    summary: str,
) -> list[dict[str, Any]]:
    """Rebuild only the stable system prefix around a replacement summary."""
    return compaction.summary_transcript_builder(summary)


class RequestCompactor:
    def __init__(self, preparation: PromptPreparation) -> None:
        self.preparation = preparation

    async def summarize_provider_compaction(
        self,
        state: ModelRequestState,
        response: LLMResponse,
        *,
        current_request_boundary: int | None,
    ) -> None:
        """Materialize the exact input replaced by provider-native compaction."""
        compaction = state.compaction
        if response.provider_compaction_applied:
            # Native compaction can omit results while the local transcript keeps
            # their full text. They no longer prove what the model can read.
            replaced_messages = (
                compaction.accepted_messages
                if response.provider_compaction_scope == "prior_context"
                else state.messages or []
            )
            state.compacted_tool_results.update(
                message["tool_call_id"]
                for message in replaced_messages
                if message.get("role") == "tool" and isinstance(message.get("tool_call_id"), str)
            )
            if response.provider_compaction_event_id is None:
                response.provider_compaction_event_id = uuid4().hex
                await shield_and_drain(
                    state.events.emit(
                        ContextCompactionEvent(
                            response.provider_compaction_event_id,
                            "succeeded",
                            reason="provider_native",
                        )
                    )
                )
        if (
            not response.provider_compaction_applied
            or response.provider_compaction_state is None
            or compaction.consolidate_provider_compaction is None
        ):
            return

        if response.provider_compaction_scope == "prior_context":
            accepted_messages = compaction.accepted_messages
            transcript_boundary = compaction.raw_accepted_boundary
        elif (
            response.provider_compaction_scope == "current_request"
            and state.messages is not None
            and current_request_boundary is not None
        ):
            accepted_messages = state.messages
            transcript_boundary = current_request_boundary
        else:
            logger.warning(
                "Ignoring provider compaction with missing request-boundary scope for {}",
                state.config.session_key or "default",
            )
            return

        summary = await compaction.consolidate_provider_compaction(
            response.provider_compaction_state,
            await self.preparation.run(deepcopy, accepted_messages),
            compaction.active_summary,
        )
        if not summary:
            return
        compaction.active_summary = summary
        compaction.summary_checkpoint = SessionSummaryCheckpoint(
            summary=summary,
            transcript_boundary=transcript_boundary,
        )

    async def compact_history(
        self,
        state: ModelRequestState,
        compaction: ContextCompactionState,
        messages: list[dict[str, Any]],
        pressure: tuple[int, str],
        *,
        tool_definitions: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        """Replace accepted history H with a checkpoint while preserving delta."""
        measured, _source = pressure
        compaction_id = uuid4().hex
        await state.events.emit(
            ContextCompactionEvent(
                compaction_id=compaction_id, phase="started", reason="context_pressure"
            ),
        )
        try:
            delta_messages = await self.preparation.run(
                compaction.delta_after_accepted,
                messages,
            )
            consolidation_prefix = await self.preparation.run(
                prepare_messages,
                state.config,
                compaction.accepted_messages,
            )
            summary = await compaction.consolidate_history(
                await self.preparation.run(deepcopy, consolidation_prefix),
                compaction.active_summary,
            )
            if not summary:
                raise ContextWindowExceededError(
                    session_key=state.config.session_key,
                    estimated_tokens=measured,
                    input_budget=input_budget(state.config),
                    source=_source,
                )

            # Fresh user input defines the next task. Only ongoing work without
            # new user input needs a temporary instruction to resume after H is replaced.
            continuation = (
                []
                if any(
                    message.get("role") == "user" and not is_hidden_history_message(message)
                    for message in delta_messages
                )
                else [{"role": "user", "content": SUMMARY_CONTINUATION_TEXT}]
            )
            summary_transcript = await self.preparation.run(
                _summary_transcript,
                compaction,
                summary,
            )
            prepared = await self.preparation.run(
                prepare_messages,
                state.config,
                [
                    *summary_transcript,
                    *continuation,
                    *delta_messages,
                ],
            )
            prepared, replacements = await self.preparation.run(
                fit_pending_file_reads,
                state.config,
                prepared,
                delta_messages,
                tool_definitions=tool_definitions,
            )
            context_tokens, _ = await self.preparation.run(
                budget.estimate_prompt_tokens_chain,
                state.config.provider,
                state.config.model,
                prepared,
                tool_definitions,
            )
            # Commit only after the complete request fits, on the owning loop.
            # Source files remain available for a narrower read. Previously
            # accepted results and all tool call/result pairs remain unchanged.
            for message in compaction.raw_messages[compaction.raw_accepted_boundary :]:
                if message.get("role") == "tool" and message.get("tool_call_id") in replacements:
                    message["content"] = replacements[message["tool_call_id"]]
            # Responses-style state is append-only. Replacing H with a
            # checkpoint requires a fresh request; a successful response may
            # establish a new provider-owned state at the rewritten boundary.
            state.conversation.replace_transcript(compaction.raw_messages)
            state.usage = None
            compaction.active_summary = summary
            compaction.checkpoint_reminded = False
            compaction.summary_checkpoint = SessionSummaryCheckpoint(
                summary=summary,
                transcript_boundary=compaction.raw_accepted_boundary,
            )
        except (Exception, asyncio.CancelledError) as exc:
            await state.events.emit(
                ContextCompactionEvent(
                    compaction_id=compaction_id,
                    phase="cancelled" if isinstance(exc, asyncio.CancelledError) else "failed",
                    reason="context_pressure",
                    error=None
                    if isinstance(exc, asyncio.CancelledError)
                    else f"{type(exc).__name__}: {exc}"[:1000],
                ),
            )
            raise
        await state.events.emit(
            ContextCompactionEvent(
                compaction_id=compaction_id,
                phase="succeeded",
                reason="context_pressure",
                context_tokens=context_tokens,
                context_window_tokens=state.config.context_window_tokens,
                context_estimated=True,
                evidence_checkpoint=isinstance(summary, EvidenceCheckpoint),
            ),
        )
        return prepared
