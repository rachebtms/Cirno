"""Accepted model history and the unsent delta for one execution."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from cirno_core.agent.context import TranscriptInput
from cirno_core.agent.governance.contracts import (
    HistoryConsolidator,
    ProviderCompactionConsolidator,
    SummaryTranscriptBuilder,
    TranscriptBuilder,
)
from cirno_core.session.summary import (
    SessionSummaryCheckpoint,
)


@dataclass(slots=True)
class ContextCompactionState:
    """Track accepted provider input H separately from the unsent delta."""

    raw_messages: list[dict[str, Any]]
    accepted_messages: list[dict[str, Any]]
    raw_accepted_boundary: int
    active_summary: str | None
    summary_transcript_builder: SummaryTranscriptBuilder
    consolidate_history: HistoryConsolidator
    consolidate_provider_compaction: ProviderCompactionConsolidator | None
    summary_checkpoint: SessionSummaryCheckpoint | None = None
    checkpoint_reminded: bool = False

    @classmethod
    def from_transcript(
        cls,
        transcript_input: TranscriptInput,
        transcript_builder: TranscriptBuilder,
        consolidate_history: HistoryConsolidator,
        consolidate_provider_compaction: ProviderCompactionConsolidator | None,
    ) -> tuple[list[dict[str, Any]], ContextCompactionState]:
        """Build the raw transcript and its initial H/delta boundary."""
        messages = list(transcript_builder(transcript_input))
        accepted_history_boundary = 1 + len(transcript_input.history)

        def build_summary_transcript(summary: str) -> list[dict[str, Any]]:
            return transcript_builder(
                replace(
                    transcript_input,
                    history=[],
                    current_message=None,
                    media=None,
                    session_summary={
                        "text": summary,
                        "last_active": datetime.now().astimezone().isoformat(),
                    },
                    runtime_context_blocks=None,
                )
            )

        return messages, cls(
            raw_messages=messages,
            accepted_messages=deepcopy(messages[:accepted_history_boundary]),
            raw_accepted_boundary=accepted_history_boundary,
            active_summary=(
                transcript_input.session_summary["text"]
                if transcript_input.session_summary is not None
                else None
            ),
            summary_transcript_builder=build_summary_transcript,
            consolidate_history=consolidate_history,
            consolidate_provider_compaction=consolidate_provider_compaction,
        )

    @classmethod
    def from_messages(
        cls,
        messages: list[dict[str, Any]],
        consolidate_history: HistoryConsolidator,
        consolidate_provider_compaction: ProviderCompactionConsolidator | None,
    ) -> ContextCompactionState:
        """Create compaction state for a standalone runner transcript."""
        raw_messages = messages
        instruction_prefix: list[dict[str, Any]] = []
        for message in raw_messages:
            if message.get("role") not in {"system", "developer"}:
                break
            instruction_prefix.append(dict(message))

        def build_summary_transcript(summary: str) -> list[dict[str, Any]]:
            archived_context = (
                f"[Archived Context Summary]\n\nPrevious conversation summary:\n{summary}"
            )
            prefix = deepcopy(instruction_prefix)
            for index in range(len(prefix) - 1, -1, -1):
                content = prefix[index].get("content")
                if isinstance(content, str):
                    prefix[index]["content"] = f"{content}\n\n---\n\n{archived_context}"
                    return prefix
            return [{"role": "system", "content": archived_context}, *prefix]

        return cls(
            raw_messages=raw_messages,
            accepted_messages=deepcopy(raw_messages),
            raw_accepted_boundary=len(raw_messages),
            active_summary=None,
            summary_transcript_builder=build_summary_transcript,
            consolidate_history=consolidate_history,
            consolidate_provider_compaction=consolidate_provider_compaction,
        )

    def request_messages(
        self,
        raw_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            *deepcopy(self.accepted_messages),
            *deepcopy(raw_messages[self.raw_accepted_boundary :]),
        ]

    def delta_after_accepted(
        self,
        request_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return deepcopy(request_messages[len(self.accepted_messages) :])
