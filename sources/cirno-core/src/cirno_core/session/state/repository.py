"""Detached session records and post-commit snapshot publication."""

from __future__ import annotations

import threading
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from typing import Any, TypeVar, cast

from cirno_core.session.model import Session, SessionIdentity, SessionPolicy
from cirno_core.session.recovery.contracts import TURN_STATE_METADATA_KEYS
from cirno_core.session.sqlite_store import SessionConflictError, SqliteSessionStore
from cirno_core.session.types import SessionTypes

_T = TypeVar("_T")


class SessionRepository:
    """Keep private records behind a transaction and expose detached owner drafts."""

    def __init__(
        self,
        store: SqliteSessionStore,
        *,
        on_delete: Callable[[str], None] | None = None,
        types: SessionTypes | None = None,
    ) -> None:
        self.store = store
        self.on_delete = on_delete
        self.types = types if types is not None else SessionTypes()
        self.snapshots: dict[str, Session] = {}
        self.transients: dict[str, Session] = {}
        self.policies: dict[str, SessionPolicy] = {}
        # A late key-only mutation cannot recreate a deleted generation.
        self.retired: set[str] = set()
        self.lock = threading.RLock()

    def change(
        self,
        key: str,
        change: Callable[[Session], _T],
        *,
        history: bool = True,
        create_if_missing: bool = False,
    ) -> _T:
        # Hold the cross-process lock across read/modify/write, not just the write.
        # No live cache can expose uncommitted changes if validation or I/O fails.
        def commit() -> tuple[Session, _T, bool]:
            session = self.load(key, history=history)
            if session is None:
                if not create_if_missing:
                    raise SessionConflictError("session does not exist")
                with self.lock:
                    self.retired.discard(key)
                session = Session(key=key)
            before = list(session.messages)
            result = change(session)
            publish_history = history
            if not history and session.persisted and session.policy.persist:
                self.store.replace_metadata(key, session.metadata, updated_at=session.updated_at)
                session.revision += 1
            else:
                self.commit(session, message_start=self.changed_start(before, session.messages))
                publish_history = True
            return session, result, publish_history

        session, result, publish_history = self.store.run_write(commit)
        self.publish(session, history=publish_history)
        if isinstance(result, Session):
            # Only import returns a session; it must not expose the committed records.
            return cast(_T, self.draft(result))
        return result

    @staticmethod
    def working(session: Session) -> Session:
        """Copy mutable headers and the list, sharing only owner-private message records."""
        return replace(
            session,
            _baseline=None,
            messages=list(session.messages),
            metadata=deepcopy(session.metadata),
            provider_state=deepcopy(session.provider_state),
        )

    def load(self, key: str, *, history: bool = True) -> Session | None:
        with self.lock:
            transient = self.transients.get(key)
            if transient is not None:
                return self.working(transient)

        def load() -> Session | None:
            session = self.store.load(key, history=False)
            if session is not None and history:
                with self.lock:
                    cached = self.snapshots.get(key)
                    if cached is not None and (cached.revision, cached.generation) == (
                        session.revision,
                        session.generation,
                    ):
                        return replace(session, messages=list(cached.messages))
                return self.store.load(key)
            return session

        session = self.store.run_read(load)
        with self.lock:
            policy = self.policies.get(key)
        if session is not None and policy is not None:
            session.policy = policy
        return session

    @staticmethod
    def changed_start(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> int:
        return next(
            (i for i, (old, new) in enumerate(zip(before, after)) if old != new),
            min(len(before), len(after)),
        )

    @staticmethod
    def copy_changed_messages(
        source: list[dict[str, Any]],
        owned: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Reuse this owner's unchanged records and detach replacements from the source."""
        return [
            owned[i] if i < len(owned) and message == owned[i] else deepcopy(message)
            for i, message in enumerate(source)
        ]

    def commit(self, session: Session, *, message_start: int = 0) -> None:
        raw = replace(session, _baseline=None)
        if session.policy.persist:
            self.store.save(raw, message_start=message_start)
            session.revision = raw.revision
            session.persisted = raw.persisted
        else:
            with self.lock:
                self.transients[session.key] = self.working(raw)

    def publish(self, session: Session, *, history: bool = True) -> None:
        """Publish owner-private records only after the enclosing transaction committed."""
        with self.lock:
            if not history:
                cached = self.snapshots.get(session.key)
                if cached is None or (cached.revision + 1, cached.generation) != (
                    session.revision,
                    session.generation,
                ):
                    self.snapshots.pop(session.key, None)
                    return
                session = replace(session, messages=cached.messages)
            self.snapshots[session.key] = self.working(session)
            if len(self.snapshots) > 8:
                self.snapshots.pop(next(iter(self.snapshots)))

    @staticmethod
    def draft(
        session: Session,
        *,
        present: bool = True,
        previous: Session | None = None,
    ) -> Session:
        raw = replace(session, _baseline=None)
        if previous is None:
            draft = deepcopy(raw)
        else:
            # Retain records already owned by this caller; copy only merged changes.
            messages = SessionRepository.copy_changed_messages(raw.messages, previous.messages)
            draft = replace(
                raw,
                messages=messages,
                metadata=deepcopy(raw.metadata),
                provider_state=deepcopy(raw.provider_state),
            )
        draft._baseline = raw  # pyright: ignore[reportPrivateUsage]
        draft.persisted = present
        return draft

    def peek(self, key: str) -> Session | None:
        """Return a detached committed view without storage I/O."""
        with self.lock:
            session = self.transients.get(key) or self.snapshots.get(key)
        # Published records are replaced, never mutated. Copying a stable view
        # outside the lock lets narrow controls read while history is detached.
        return self.draft(session) if session is not None else None

    def peek_metadata(self, key: str, *, include_runtime: bool = True) -> dict[str, Any] | None:
        """Return detached committed metadata without copying conversation history."""
        with self.lock:
            session = self.transients.get(key) or self.snapshots.get(key)
        if session is None:
            return None
        metadata = (
            session.metadata
            if include_runtime
            else {
                name: value
                for name, value in session.metadata.items()
                if name not in TURN_STATE_METADATA_KEYS
            }
        )
        return deepcopy(metadata)

    def peek_identity(self, key: str) -> SessionIdentity | None:
        """Read immutable identity and policy without copying history or checkpoints."""
        with self.lock:
            session = self.transients.get(key) or self.snapshots.get(key)
            return (
                SessionIdentity(session.generation, session.policy) if session is not None else None
            )

    def peek_header(self, key: str, *, include_runtime: bool = True) -> Session | None:
        """Read cached policy and metadata without detaching message history."""
        with self.lock:
            session = self.transients.get(key) or self.snapshots.get(key)
        if session is None:
            return None
        metadata = (
            session.metadata
            if include_runtime
            else {
                name: value
                for name, value in session.metadata.items()
                if name not in TURN_STATE_METADATA_KEYS
            }
        )
        header = replace(
            session,
            messages=[],
            metadata=deepcopy(metadata),
            provider_state=None,
            _baseline=None,
        )
        header.last_archived = session.last_archived
        return header
