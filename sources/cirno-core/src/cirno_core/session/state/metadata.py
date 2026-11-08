"""Short metadata commands, display projections and stable handles."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextvars import copy_context
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from cirno_core.session.model import Session
from cirno_core.session.recovery.contracts import TURN_STATE_METADATA_KEYS
from cirno_core.session.sqlite_store import SessionConflictError

from .operations import SessionOperations
from .repository import SessionRepository

_T = TypeVar("_T")


@dataclass
class SessionMetadata:
    repository: SessionRepository
    operations: SessionOperations

    async def mutate_metadata(
        self,
        key: str,
        change: Callable[[dict[str, Any]], _T],
        *,
        expected_generation: str | None = None,
        create_if_missing: bool = False,
    ) -> tuple[_T, dict[str, Any]]:
        """Run a synchronous metadata command inside one short transaction."""

        def commit() -> tuple[_T, dict[str, Any]]:
            def write() -> tuple[Session, _T, bool]:
                session = self.repository.load(key, history=False)
                if session is None:
                    with self.repository.lock:
                        retired = key in self.repository.retired
                    if retired or not create_if_missing:
                        raise SessionConflictError("session does not exist")
                    session = Session(key=key)
                if expected_generation is not None and session.generation != expected_generation:
                    raise SessionConflictError("metadata command belongs to a replaced session")
                result = change(session.metadata)
                header_only = session.policy.persist and session.persisted
                if header_only:
                    self.repository.store.replace_metadata(key, session.metadata)
                    session.revision += 1
                else:
                    self.repository.commit(session)
                return session, result, header_only

            session, result, header_only = self.repository.store.run_write(write)
            self.repository.publish(session, history=not header_only)
            return deepcopy(result), deepcopy(session.metadata)

        return await self.operations.execute(key, commit)

    async def open_with_metadata(
        self,
        key: str,
        updates: Mapping[str, Any],
        *,
        expected_generation: str | None = None,
        validate_existing: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> tuple[str, bool]:
        """Open one generation and atomically validate and attach admission metadata."""
        values = deepcopy(dict(updates))
        if TURN_STATE_METADATA_KEYS.intersection(values):
            raise ValueError("turn state must be changed through turn operations")

        def open_session() -> tuple[str, bool]:
            def write() -> tuple[Session | None, bool, bool, str]:
                with self.repository.lock:
                    transient = key in self.repository.transients
                if not transient:
                    header = self.repository.store.read_metadata(key, include_runtime=False)
                    if header is not None and all(
                        name in header["metadata"] and header["metadata"][name] == value
                        for name, value in values.items()
                    ):
                        version = self.repository.store.read_version(key)
                        assert version is not None
                        if expected_generation is not None and version[0] != expected_generation:
                            raise SessionConflictError(
                                "session admission belongs to a replaced session"
                            )
                        if validate_existing is not None:
                            validate_existing(header["metadata"])
                        # Most sends reuse their workspace. Neither deserialize nor
                        # rewrite the potentially large in-flight model checkpoint.
                        return None, False, False, version[0]
                session = self.repository.load(key, history=False)
                created = session is None
                if created:
                    if expected_generation is not None:
                        raise SessionConflictError("session does not exist")
                    with self.repository.lock:
                        self.repository.retired.discard(key)
                    session = Session(key=key)
                elif expected_generation is not None and session.generation != expected_generation:
                    raise SessionConflictError("session admission belongs to a replaced session")
                if not created and validate_existing is not None:
                    validate_existing(session.metadata)
                session.metadata.update(values)
                header_only = session.policy.persist and session.persisted
                if header_only:
                    self.repository.store.replace_metadata(key, session.metadata)
                    session.revision += 1
                else:
                    self.repository.commit(session)
                return session, created, header_only, session.generation

            session, created, header_only, generation = self.repository.store.run_write(write)
            if session is not None:
                self.repository.publish(session, history=not header_only)
            return generation, created

        return await self.operations.execute(key, open_session, operation_name="open_with_metadata")

    async def read_metadata(
        self, key: str, *, include_runtime: bool = True
    ) -> dict[str, Any] | None:
        def read() -> dict[str, Any] | None:
            with self.repository.lock:
                transient = self.repository.transients.get(key)
                if transient is not None:
                    metadata = (
                        transient.metadata
                        if include_runtime
                        else {
                            name: value
                            for name, value in transient.metadata.items()
                            if name not in TURN_STATE_METADATA_KEYS
                        }
                    )
                    return {"key": key, "metadata": deepcopy(metadata)}
            return cast(
                dict[str, Any] | None,
                self.repository.store.read_metadata(key, include_runtime=include_runtime),
            )

        return await self.operations.execute(key, read, write=False)

    async def list_metadata(self) -> list[dict[str, Any]]:
        return await self.query_metadata(lambda rows: rows)

    async def query_metadata(
        self,
        project: Callable[[list[dict[str, Any]]], _T],
    ) -> _T:
        """Read one committed display snapshot without waiting for active turns.

        Admission and shutdown still belong to this owner. Unlike an ordered
        mutation or session read, a sidebar snapshot may precede pending writes.
        Project detached rows on the reader after its SQL transaction closes.
        """
        context = copy_context()

        def read() -> _T:
            return context.run(project, self.repository.store.list_metadata())

        async def query() -> _T:
            return await self.operations.run(read, write=False)

        return await self.operations.submit(
            None,
            query,
            operation_name="query_metadata",
            barrier=False,
        )

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
        values = deepcopy(dict(updates))
        removed = tuple(remove)
        if TURN_STATE_METADATA_KEYS.intersection(values) or TURN_STATE_METADATA_KEYS.intersection(
            removed
        ):
            raise ValueError("turn state must be changed through turn operations")

        def change(metadata: dict[str, Any]) -> None:
            for name in removed:
                metadata.pop(name, None)
            metadata.update(values)

        await self.mutate_metadata(
            key,
            change,
            expected_generation=expected_generation,
            create_if_missing=create_if_missing,
        )
