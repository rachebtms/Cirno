"""Canonical history and delivered-message recording."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, TypeVar

from cirno_core.session.archive_contract import ArchiveWriter
from cirno_core.session.display_history import HistoryFact, HistoryReader
from cirno_core.session.model import Session
from cirno_core.session.sqlite_store import SessionConflictError

from .operations import SessionOperations
from .repository import SessionRepository

_T = TypeVar("_T")


@dataclass
class SessionHistory:
    repository: SessionRepository
    operations: SessionOperations

    async def project_history(
        self,
        key: str,
        project: Callable[[HistoryReader], _T],
    ) -> _T:
        return await self.operations.execute(
            key,
            lambda: self.repository.store.project_history(key, project),
            operation_name="project_history",
            write=False,
        )

    async def append_history(
        self,
        key: str,
        facts: Sequence[HistoryFact],
        *,
        expected_generation: str | None,
    ) -> None:
        """Append to an existing session; None selects its current generation."""
        records = list(facts)
        await self.operations.execute(
            key,
            lambda: self.repository.store.append_history(
                key, deepcopy(records), expected_generation=expected_generation
            ),
            operation_name="append_history",
        )
        from cirno_core.observability.recordings import current_recordings

        recordings = current_recordings()
        if recordings.active:
            await asyncio.to_thread(recordings.facts, key, records)

    async def append_internal_input(
        self, key: str, fact: HistoryFact, *, identifier: str, expected_generation: str | None
    ) -> bool:
        """Atomically persist an internal input and its replay receipt."""
        import hashlib

        digest = hashlib.sha256(fact.encode().encode()).hexdigest()
        receipt_id = "internal-display:" + identifier

        def write() -> bool:
            header = self.repository.store.load(key, history=False)
            if (
                header is None
                or expected_generation is not None
                and header.generation != expected_generation
            ):
                raise SessionConflictError(
                    "internal input belongs to a deleted or replaced session"
                )
            generation = header.generation
            if self.repository.store.inbox_receipt(key, generation, receipt_id) is not None:
                return False
            self.repository.store.append_history(key, [fact], expected_generation=generation)
            self.repository.store.record_inbox_receipt(
                key, generation, receipt_id, receipt_id, digest
            )
            self.repository.store.mark_inbox_read(key, generation, [receipt_id])
            return True

        return await self.operations.execute(
            key,
            lambda: self.repository.store.run_write(write),
            operation_name="append_internal_input",
        )

    async def record_delivery(
        self,
        key: str,
        content: str,
        extra: Mapping[str, Any],
        *,
        expected_generation: str,
    ) -> None:
        """Append a delivery only to the existing generation it belongs to."""
        if not expected_generation:
            raise ValueError("delivery requires a session generation")
        values = deepcopy(dict(extra))

        def change(session: Session) -> None:
            if session.generation != expected_generation:
                raise SessionConflictError("delivery belongs to a replaced session")
            session.add_message("assistant", content, **values)

        await self.operations.execute(
            key,
            lambda: self.repository.change(key, change),
            operation_name="record_delivery",
        )

    async def release_archived_runtime(self, key: str, archive: ArchiveWriter) -> int:
        """Release only committed archived input, never transient or privacy-disabled state."""

        def release():
            with self.repository.lock:
                policy = self.repository.policies.get(key)
                if (
                    key in self.repository.transients
                    or policy
                    and (not policy.persist or not policy.log_content)
                ):
                    return 0
            count = self.repository.store.release_archived_runtime(key, archive)
            if count:
                with self.repository.lock:
                    self.repository.snapshots.pop(key, None)
            return count

        return await self.operations.execute(
            key, release, operation_name="release_archived_runtime"
        )

    async def has_unarchived_messages(self, key: str) -> bool:
        """Check committed archive eligibility without returning a turn draft."""
        return await self.operations.execute(
            key,
            lambda: self.repository.store.has_unarchived_messages(key),
            operation_name="has_unarchived_messages",
            write=False,
        )
