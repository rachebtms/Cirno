"""Incremental, atomic recovery boundaries for a model run."""

from __future__ import annotations

from typing import Any, cast

from cirno_core.providers.contracts import ProviderConversationState
from cirno_core.session.model import Session
from cirno_core.session.recovery.contracts import (
    PROVIDER_STATE_CHECKPOINT_VERSION,
    PROVIDER_STATE_CHECKPOINT_VERSION_KEY,
)
from cirno_core.session.summary import SessionSummaryCheckpoint

from .persistence import TurnPersistence


class RuntimeCheckpointWriter:
    def __init__(self, persistence: TurnPersistence, session: Session, *, start: int,
                 history_boundary: int,
                 input_persisted_early: bool) -> None:
        self.persistence, self.session = persistence, session
        self.cursor = start
        self.persisted_count = 0
        self.summary: SessionSummaryCheckpoint | None = None
        # Raw prompt indices differ from persisted positions (system context,
        # filtered rows and hidden consolidation markers are not one-to-one).
        self.positions = {start: len(session.messages)}
        # Pre-request consolidation covers accepted history, excluding the fresh
        # input even when a continuation deliberately does not persist that input.
        self.positions[history_boundary] = len(session.messages) - int(input_persisted_early)

    async def __call__(self, payload: dict[str, Any]) -> None:
        public = dict(payload)
        transcript = cast(list[dict[str, Any]], public.pop("_transcript"))
        summary = cast(SessionSummaryCheckpoint | None, public.pop("_summary_checkpoint"))
        private = public.pop("provider_state", None)
        public.pop(PROVIDER_STATE_CHECKPOINT_VERSION_KEY, None)
        if "provider_state" in payload and (
            private is None or isinstance(private, ProviderConversationState)
        ):
            self.session.provider_state = private
            public[PROVIDER_STATE_CHECKPOINT_VERSION_KEY] = PROVIDER_STATE_CHECKPOINT_VERSION
        await self.persistence.checkpoint(
            self.session, public, messages=transcript, skip=self.cursor,
            summary_checkpoint=summary if summary != self.summary else None,
            message_positions=self.positions,
        )
        self.cursor = self.persisted_count = len(transcript)
        if summary is not None:
            self.summary = summary
