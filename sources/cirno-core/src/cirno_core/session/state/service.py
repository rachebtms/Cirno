"""Session state facade; domain services share one repository and operation owner."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar

from cirno_core.bus.events import InboundMessage
from cirno_core.session.archive_contract import ArchiveWriter
from cirno_core.session.display_history import HistoryFact, HistoryReader
from cirno_core.session.model import Session, SessionIdentity, SessionPolicy
from cirno_core.session.sqlite_store import SqliteSessionStore
from cirno_core.session.types import SessionTypes

from .access import SessionAccess
from .branches import SessionBranches
from .history import SessionHistory
from .handles import SessionHandles
from .inbox import SessionInbox
from .lifecycle import SessionLifecycle
from .metadata import SessionMetadata
from .operations import DEFAULT_CAPACITY, DEFAULT_WORKERS, SessionOperations
from .repository import SessionRepository
from .turns import SessionTurns

_T = TypeVar("_T")


class SessionState:
    """Expose ordered session operations without sharing live mutable records."""

    def __init__(
        self,
        store: SqliteSessionStore,
        *,
        capacity: int = DEFAULT_CAPACITY,
        workers: int = DEFAULT_WORKERS,
        on_delete: Callable[[str], None] | None = None,
        types: SessionTypes | None = None,
    ) -> None:
        self.repository = SessionRepository(store, on_delete=on_delete, types=types)
        self.operations = SessionOperations(store, capacity=capacity, workers=workers)
        self.access = SessionAccess(self.repository, self.operations)
        self.turns = SessionTurns(self.repository, self.operations)
        self.metadata = SessionMetadata(self.repository, self.operations)
        self.handles = SessionHandles(self.repository, self.operations)
        self.history = SessionHistory(self.repository, self.operations)
        self.inbox = SessionInbox(self.repository, self.operations)
        self.branches = SessionBranches(self.repository, self.operations)
        self.lifecycle = SessionLifecycle(self.repository, self.operations)

    @property
    def is_bound(self) -> bool:
        return self.operations.is_bound

    @property
    def bound_loop(self) -> asyncio.AbstractEventLoop | None:
        return self.operations.bound_loop

    async def aclose(self) -> None:
        await self.operations.aclose()

    def peek(self, key: str) -> Session | None:
        """Return a detached committed view without storage I/O."""
        return self.repository.peek(key)

    def peek_metadata(self, key: str, *, include_runtime: bool = True) -> dict[str, Any] | None:
        """Return detached committed metadata without copying conversation history."""
        return self.repository.peek_metadata(key, include_runtime=include_runtime)

    def peek_identity(self, key: str) -> SessionIdentity | None:
        """Read immutable identity and policy without copying history or checkpoints."""
        return self.repository.peek_identity(key)

    def peek_header(self, key: str, *, include_runtime: bool = True) -> Session | None:
        """Read cached policy and metadata without detaching message history."""
        return self.repository.peek_header(key, include_runtime=include_runtime)

    async def set_policy(self, key: str, policy: SessionPolicy) -> None:
        """Configure runtime privacy and tools for an existing durable session."""
        return await self.access.set_policy(key, policy)

    async def register_transient(
        self, key: str, *, disabled_tools: frozenset[str] = frozenset()
    ) -> Session:
        """Create an owner-held non-persistent session for a temporary conversation."""
        return await self.access.register_transient(key, disabled_tools=disabled_tools)

    async def read(self, key: str) -> Session | None:
        """Return a detached view of committed state; edits do not write through."""
        return await self.access.read(key)

    async def get(self, key: str) -> Session:
        """Read an existing conversation; create missing state on the writer."""
        return await self.access.get(key)

    async def get_header(self, key: str) -> Session:
        """Read or create a header for controls, without issuing a turn draft."""
        return await self.access.get_header(key)

    async def read_header(self, key: str) -> Session | None:
        """Read an existing header without loading history or recreating deleted state."""
        return await self.access.read_header(key)

    async def create_child(
        self,
        parent_key: str,
        key: str,
        *,
        metadata: Mapping[str, Any],
        content: str,
        policy: SessionPolicy,
    ) -> Session:
        """Establish a child and its parent before execution leaves the owner."""
        return await self.access.create_child(
            parent_key, key, metadata=metadata, content=content, policy=policy
        )

    async def mutate_metadata(
        self,
        key: str,
        change: Callable[[dict[str, Any]], _T],
        *,
        expected_generation: str | None = None,
        create_if_missing: bool = False,
    ) -> tuple[_T, dict[str, Any]]:
        """Run a synchronous metadata command inside one short transaction."""
        return await self.metadata.mutate_metadata(
            key,
            change,
            expected_generation=expected_generation,
            create_if_missing=create_if_missing,
        )

    async def open_with_metadata(
        self,
        key: str,
        updates: Mapping[str, Any],
        *,
        expected_generation: str | None = None,
        validate_existing: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> tuple[str, bool]:
        """Open one generation and atomically validate and attach admission metadata."""
        return await self.metadata.open_with_metadata(
            key,
            updates,
            expected_generation=expected_generation,
            validate_existing=validate_existing,
        )

    async def prepare_input(self, session: Session) -> None:
        """Commit the prepared input and recovery baseline before external execution."""
        return await self.turns.prepare_input(session)

    async def finish_turn(self, session: Session) -> None:
        """Commit the assembled transcript and clear its recovery markers."""
        return await self.turns.finish_turn(session)

    async def restore_interruption(self, session: Session) -> None:
        """Commit a recovery decision against the version it classified."""
        return await self.turns.restore_interruption(session)

    async def checkpoint_view(self, draft: Session, payload: Mapping[str, Any]) -> None:
        """Store a turn's recovery boundary without publishing unrelated draft edits."""
        return await self.turns.checkpoint_view(draft, payload)

    async def project_history(self, key: str, project: Callable[[HistoryReader], _T]) -> _T:
        return await self.history.project_history(key, project)

    async def append_history(
        self, key: str, facts: Sequence[HistoryFact], *, expected_generation: str | None
    ) -> None:
        """Append to an existing session; None selects its current generation."""
        return await self.history.append_history(
            key, facts, expected_generation=expected_generation
        )

    async def append_internal_input(
        self, key: str, fact: HistoryFact, *, identifier: str, expected_generation: str | None
    ) -> bool:
        """Atomically persist an internal input and its replay receipt."""
        return await self.history.append_internal_input(
            key, fact, identifier=identifier, expected_generation=expected_generation
        )

    async def record_delivery(
        self, key: str, content: str, extra: Mapping[str, Any], *, expected_generation: str
    ) -> None:
        """Append a delivery only to the existing generation it belongs to."""
        return await self.history.record_delivery(
            key, content, extra, expected_generation=expected_generation
        )

    async def queue_followup(self, key: str, message: InboundMessage) -> str | None:
        return await self.inbox.queue_followup(key, message)

    async def acknowledge_followups(self, key: str, identifiers: Sequence[str]) -> None:
        return await self.inbox.acknowledge_followups(key, identifiers)

    async def release_archived_runtime(self, key: str, archive: ArchiveWriter) -> int:
        """Release only committed archived input, never transient or privacy-disabled state."""
        return await self.history.release_archived_runtime(key, archive)

    async def commit_summary(self, source: Session, summary: str, *, archive_end: int) -> None:
        return await self.turns.commit_summary(source, summary, archive_end=archive_end)

    async def read_metadata(
        self, key: str, *, include_runtime: bool = True
    ) -> dict[str, Any] | None:
        return await self.metadata.read_metadata(key, include_runtime=include_runtime)

    async def has_unarchived_messages(self, key: str) -> bool:
        """Check committed archive eligibility without returning a turn draft."""
        return await self.history.has_unarchived_messages(key)

    async def list_sessions(self) -> list[dict[str, Any]]:
        return await self.lifecycle.list_sessions()

    async def list_metadata(self) -> list[dict[str, Any]]:
        return await self.metadata.list_metadata()

    async def query_metadata(self, project: Callable[[list[dict[str, Any]]], _T]) -> _T:
        """Read one committed display snapshot without waiting for active turns."""
        return await self.metadata.query_metadata(project)

    async def ensure_session_handles(self) -> dict[str, str]:
        """Allocate stable public handles through the runtime mutation owner."""
        return await self.handles.ensure_session_handles()

    async def rename_session_handle(self, key: str, name: str) -> dict[str, str]:
        return await self.handles.rename(key, name)

    async def prune_dream_sessions(self, *, keep: int = 10) -> int:
        """Delete older Dream conversations in one transaction on the owner worker."""
        return await self.lifecycle.prune_dream_sessions(keep=keep)

    def forget_transient(self, key: str) -> None:
        """Drop process-local cache state; runtime disposal should use discard()."""
        return self.lifecycle.forget_transient(key)

    async def discard(self, key: str) -> None:
        return await self.lifecycle.discard(key)

    async def edit_user_input(self, key: str, turn_id: str, content: str) -> InboundMessage:
        """Rewind a human prompt and durably queue its replacement atomically."""
        return await self.branches.edit_user_input(key, turn_id, content)

    async def fork(
        self,
        source_key: str,
        target_key: str,
        before_user_index: int,
        *,
        title: str | None = None,
        history_projection: Callable[[Session], list[HistoryFact]] | None = None,
    ) -> Session | None:
        return await self.branches.fork(
            source_key,
            target_key,
            before_user_index,
            title=title,
            history_projection=history_projection,
        )

    async def delete(self, key: str, *, expected_generation: str | None = None) -> bool:
        return await self.lifecycle.delete(key, expected_generation=expected_generation)

    async def update_metadata(
        self,
        key: str,
        updates: Mapping[str, Any],
        *,
        remove: Sequence[str] = (),
        expected_generation: str | None = None,
        create_if_missing: bool = False,
    ) -> None:
        """Commit metadata changes without granting access to the live transcript."""
        return await self.metadata.update_metadata(
            key,
            updates,
            remove=remove,
            expected_generation=expected_generation,
            create_if_missing=create_if_missing,
        )

    async def import_messages(
        self,
        key: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        metadata: Mapping[str, Any] | None = None,
        require_empty: bool = False,
    ) -> Session:
        """Validate and commit an import as one operation, or leave state unchanged."""
        return await self.lifecycle.import_messages(
            key, messages, metadata=metadata, require_empty=require_empty
        )

    async def reset(self, key: str) -> None:
        """Clear the transcript and revoke any old turn in one commit."""
        return await self.lifecycle.reset(key)
