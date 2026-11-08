"""Session import, retirement, deletion and reset."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from cirno_core.session.keys import is_dream_session
from cirno_core.session.model import Session
from cirno_core.session.recovery.contracts import PENDING_USER_TURN_KEY, TURN_STATE_METADATA_KEYS
from cirno_core.session.sqlite_store import SessionConflictError
from cirno_core.session.types import PARENT_SESSION_KEY

from .operations import SessionOperations
from .repository import SessionRepository


@dataclass
class SessionLifecycle:
    repository: SessionRepository
    operations: SessionOperations

    async def list_sessions(self) -> list[dict[str, Any]]:
        return await self.operations.execute(
            None,
            lambda: cast(list[dict[str, Any]], self.repository.store.list_sessions()),
            operation_name="list_sessions",
            write=False,
        )

    async def prune_dream_sessions(self, *, keep: int = 10) -> int:
        """Delete older Dream conversations in one transaction on the owner worker."""

        def prune() -> list[str]:
            def write() -> list[str]:
                rows = [
                    row
                    for row in self.repository.store.list_sessions()
                    if is_dream_session(row["key"])
                ]
                removed = [row["key"] for row in rows[max(0, keep) :]]
                for key in removed:
                    self.repository.store.delete(key)
                return removed

            removed = self.repository.store.run_write(write)
            with self.repository.lock:
                for key in removed:
                    self.repository.transients.pop(key, None)
                    self.repository.snapshots.pop(key, None)
                    self.repository.policies.pop(key, None)
                    self.repository.retired.add(key)
            return removed

        removed = await self.operations.execute(None, prune, operation_name="prune_dream_sessions")
        if self.repository.on_delete is not None:
            for key in removed:
                self.repository.on_delete(key)
        return len(removed)

    def forget_transient(self, key: str) -> None:
        """Drop process-local cache state; runtime disposal should use discard()."""
        with self.repository.lock:
            self.repository.transients.pop(key, None)
            self.repository.snapshots.pop(key, None)

    async def discard(self, key: str) -> None:
        def discard() -> None:
            with self.repository.lock:
                self.repository.transients.pop(key, None)
                self.repository.snapshots.pop(key, None)
                self.repository.policies.pop(key, None)
                self.repository.retired.add(key)

        await self.operations.execute(key, discard, operation_name="discard")

    async def delete(
        self,
        key: str,
        *,
        expected_generation: str | None = None,
    ) -> bool:
        def delete() -> tuple[bool, set[str]]:
            def write() -> tuple[bool, set[str]]:
                session = self.repository.load(key, history=False)
                if expected_generation is not None and (
                    session is None or session.generation != expected_generation
                ):
                    raise SessionConflictError("delete belongs to a replaced session")
                rows = self.repository.store.list_metadata()
                with self.repository.lock:
                    rows.extend(
                        {"key": child.key, "metadata": child.metadata}
                        for child in self.repository.transients.values()
                    )
                children: dict[str, list[str]] = {}
                for row in rows:
                    parent = row["metadata"].get(PARENT_SESSION_KEY)
                    if isinstance(parent, str):
                        children.setdefault(parent, []).append(row["key"])
                pending = [key]
                removed: set[str] = set()
                deleted = False
                while pending:
                    current = pending.pop()
                    if current in removed:
                        continue
                    removed.add(current)
                    pending.extend(children.get(current, ()))
                    deleted = self.repository.store.delete(current) or deleted
                return deleted, removed

            deleted, removed = self.repository.store.run_write(write)
            with self.repository.lock:
                for current in removed:
                    self.repository.transients.pop(current, None)
                    self.repository.snapshots.pop(current, None)
                    self.repository.policies.pop(current, None)
                    self.repository.retired.add(current)
            return deleted, removed

        deleted, removed = await self.operations.execute(None, delete, operation_name="delete")
        if self.repository.on_delete is not None:
            for current in removed:
                self.repository.on_delete(current)
        return deleted

    async def import_messages(
        self,
        key: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        metadata: Mapping[str, Any] | None = None,
        require_empty: bool = False,
    ) -> Session:
        """Validate and commit an import as one operation, or leave state unchanged."""
        records = deepcopy([dict(message) for message in messages])
        values = deepcopy(dict(metadata or {}))
        if TURN_STATE_METADATA_KEYS.intersection(values):
            raise ValueError("cannot import active turn state as metadata")
        for record in records:
            if record.get("role") not in {"user", "assistant", "tool", "system"}:
                raise ValueError("unsupported message role")
            if "content" not in record:
                raise ValueError("messages must include content")

        def change(session: Session) -> Session:
            if session.metadata.get(PENDING_USER_TURN_KEY):
                raise SessionConflictError("cannot import into an active or interrupted session")
            if require_empty and session.messages:
                raise SessionConflictError("restore target is not empty")
            session.messages.extend(records)
            session.metadata.update(values)
            session.updated_at = datetime.now()
            return session

        return await self.operations.execute(
            key,
            lambda: self.repository.change(key, change, create_if_missing=True),
            operation_name="import_messages",
        )

    async def reset(self, key: str) -> None:
        """Clear the transcript and revoke any old turn in one commit."""

        def reset() -> None:
            def write() -> Session:
                old = self.repository.load(key, history=False)
                with self.repository.lock:
                    self.repository.retired.discard(key)
                session = Session(key=key)
                if old is not None:
                    session.policy = old.policy
                    session.metadata = deepcopy(old.metadata)
                for name in (
                    *TURN_STATE_METADATA_KEYS,
                    "webui_recovery",
                    "_last_summary",
                    "_stopped_at_iteration_limit",
                    "goal_state",
                    "thread_goal",
                    "_sustained_goal_continuation_rounds",
                    "work_report",
                    "work_report_pending",
                    "supervision_events",
                ):
                    session.metadata.pop(name, None)
                if session.policy.persist:
                    self.repository.store.delete(key)
                self.repository.commit(session)
                return session

            session = self.repository.store.run_write(write)
            self.repository.publish(session)

        await self.operations.execute(key, reset)
