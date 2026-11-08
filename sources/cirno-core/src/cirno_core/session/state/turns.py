"""Turn draft merging and recovery checkpoints."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, fields, replace
from typing import Any

from cirno_core.session.model import Session
from cirno_core.session.recovery.contracts import PENDING_USER_TURN_KEY, RUNTIME_CHECKPOINT_KEY
from cirno_core.session.sqlite_store import SessionConflictError

from .operations import SessionOperations
from .repository import SessionRepository


@dataclass
class SessionTurns:
    repository: SessionRepository
    operations: SessionOperations

    @staticmethod
    def _refresh(draft: Session, fresh: Session) -> None:
        for item in fields(Session):
            setattr(draft, item.name, getattr(fresh, item.name))

    def _apply_turn(self, draft: Session) -> tuple[Session, int]:
        from cirno_core.session.recovery.contracts import PENDING_FOLLOWUPS_KEY
        from cirno_core.session.recovery.pending import acknowledge_pending_followups

        baseline = draft._baseline  # pyright: ignore[reportPrivateUsage]
        if baseline is None:
            raise ValueError("session changes require an owner-issued draft")
        loaded = self.repository.load(draft.key)
        if (draft.persisted or not draft.policy.persist) and loaded is None:
            raise SessionConflictError("session was deleted")
        current = loaded or Session(
            key=draft.key, created_at=baseline.created_at, generation=baseline.generation
        )
        before_messages = current.messages
        if loaded is not None and (current.generation != baseline.generation):
            raise SessionConflictError("session was reset")
        for key in baseline.metadata.keys() | draft.metadata.keys():
            if key == PENDING_FOLLOWUPS_KEY:
                # queue_followup owns this journal; a draft may predate its inputs.
                continue
            missing = object()
            before = baseline.metadata.get(key, missing)
            after = draft.metadata.get(key, missing)
            if before == after:
                continue
            existing = current.metadata.get(key, missing)
            if existing != before and existing != after:
                raise SessionConflictError(f"turn metadata changed: {key}")
            if after is missing:
                current.metadata.pop(key, None)
            else:
                current.metadata[key] = deepcopy(after)
        if draft.messages != baseline.messages:
            if current.messages == baseline.messages:
                current.messages = self.repository.copy_changed_messages(
                    draft.messages, before_messages
                )
            elif (
                draft.messages[: len(baseline.messages)] == baseline.messages
                and current.messages[: len(baseline.messages)] == baseline.messages
            ):
                current.messages = current.messages + deepcopy(
                    draft.messages[len(baseline.messages) :]
                )
            else:
                raise SessionConflictError("session history changed")
        for name in ("last_archived", "provider_state"):
            before, after = getattr(baseline, name), getattr(draft, name)
            if before != after:
                existing = getattr(current, name)
                if existing != before and existing != after:
                    raise SessionConflictError(f"session {name} changed")
                setattr(current, name, deepcopy(after))
        acknowledge_pending_followups(current, draft.consumed_followup_ids)
        if current.policy.persist:
            self.repository.store.mark_inbox_read(
                current.key, current.generation, draft.consumed_followup_ids
            )
        current.policy = draft.policy
        current.updated_at = max(current.updated_at, draft.updated_at)
        return current, self.repository.changed_start(before_messages, current.messages)

    async def _submit_draft(self, draft: Session) -> None:
        def commit() -> Session:
            # The caller owns this draft and awaits settlement before using it again.
            def write() -> Session:
                current, message_start = self._apply_turn(draft)
                self.repository.commit(current, message_start=message_start)
                return current

            current = self.repository.store.run_write(write)
            self.repository.publish(current)
            return self.repository.draft(current, previous=draft)

        fresh = await self.operations.execute(draft.key, commit)
        self._refresh(draft, fresh)

    async def prepare_input(self, session: Session) -> None:
        """Commit the prepared input and recovery baseline before external execution."""
        await self._submit_draft(session)

    async def finish_turn(self, session: Session) -> None:
        """Commit the assembled transcript and clear its recovery markers."""
        session.metadata.pop(PENDING_USER_TURN_KEY, None)
        session.metadata.pop(RUNTIME_CHECKPOINT_KEY, None)
        await self._submit_draft(session)

    async def restore_interruption(self, session: Session) -> None:
        """Commit a recovery decision against the version it classified."""
        await self._submit_draft(session)

    async def checkpoint_view(self, draft: Session, payload: Mapping[str, Any]) -> None:
        """Store a turn's recovery boundary without publishing unrelated draft edits."""
        baseline = draft._baseline  # pyright: ignore[reportPrivateUsage]
        generation = baseline.generation if baseline is not None else None

        def commit() -> Session:
            request = deepcopy(dict(payload))
            provider = deepcopy(draft.provider_state)

            def write() -> Session:
                current = self.repository.load(draft.key, history=False)
                if current is None:
                    raise SessionConflictError("checkpoint requires accepted input")
                if current.generation != generation:
                    raise SessionConflictError("checkpoint belongs to a replaced session")
                current.metadata[RUNTIME_CHECKPOINT_KEY] = request
                current.provider_state = provider
                if not current.policy.persist:
                    self.repository.commit(current)
                else:
                    self.repository.store.save_runtime_checkpoint(current)
                return current

            current = self.repository.store.run_write(write)
            self.repository.publish(current, history=not current.policy.persist)
            return current

        committed = await self.operations.execute(draft.key, commit)
        # Only the checkpoint fields have committed; preserve other local changes.
        draft.metadata[RUNTIME_CHECKPOINT_KEY] = dict(payload)
        if baseline is not None:
            metadata = {
                **baseline.metadata,
                RUNTIME_CHECKPOINT_KEY: committed.metadata[RUNTIME_CHECKPOINT_KEY],
            }
            draft._baseline = replace(  # pyright: ignore[reportPrivateUsage]
                baseline, metadata=metadata, provider_state=committed.provider_state
            )

    async def commit_summary(
        self,
        source: Session,
        summary: str,
        *,
        archive_end: int,
    ) -> None:
        prefix = deepcopy(source.messages[:archive_end])

        def change(session: Session) -> None:
            if session.generation != source.generation or session.messages[:archive_end] != prefix:
                raise SessionConflictError("summarized history was replaced")
            session.commit_summary_checkpoint(
                summary,
                insert_at=archive_end,
                last_active=source.updated_at,
            )
            session.provider_state = None

        await self.operations.execute(
            source.key, lambda: self.repository.change(source.key, change)
        )
