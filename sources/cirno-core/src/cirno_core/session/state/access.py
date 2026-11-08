"""Session access, policy and child creation."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any

from cirno_core.session.model import Session, SessionPolicy
from cirno_core.session.sqlite_store import SessionConflictError
from cirno_core.session.types import PARENT_SESSION_KEY

from .operations import SessionOperations
from .repository import SessionRepository


@dataclass
class SessionAccess:
    repository: SessionRepository
    operations: SessionOperations

    async def set_policy(self, key: str, policy: SessionPolicy) -> None:
        """Configure runtime privacy and tools for an existing durable session."""
        if not policy.persist:
            raise ValueError("use register_transient for non-persistent sessions")

        def configure() -> None:
            session = self.repository.load(key)
            if session is None or not session.policy.persist:
                raise ValueError("policy requires an existing durable session")
            with self.repository.lock:
                self.repository.policies[key] = policy
            session.policy = policy
            self.repository.publish(session)

        await self.operations.execute(key, configure)

    async def register_transient(
        self,
        key: str,
        *,
        disabled_tools: frozenset[str] = frozenset(),
    ) -> Session:
        """Create an owner-held non-persistent session for a temporary conversation."""

        def register() -> Session:
            session = Session(
                key=key,
                policy=SessionPolicy(
                    persist=False,
                    log_content=False,
                    disabled_tools=disabled_tools,
                ),
            )
            with self.repository.lock:
                if key in self.repository.transients:
                    raise SessionConflictError("transient session already exists")
                self.repository.retired.discard(key)
                self.repository.transients[key] = session
            return self.repository.draft(session)

        return await self.operations.execute(key, register, operation_name="register_transient")

    async def read(self, key: str) -> Session | None:
        """Return a detached view of committed state; edits do not write through."""

        def read() -> Session | None:
            session = self.repository.load(key)
            if session is None:
                return None
            self.repository.publish(session)
            return self.repository.draft(session)

        return await self.operations.execute(key, read, write=False)

    async def get(self, key: str) -> Session:
        """Read an existing conversation; create missing state on the writer."""
        return await self._get(key, history=True)

    async def get_header(self, key: str) -> Session:
        """Read or create a header for controls, without issuing a turn draft."""
        return await self._get(key, history=False)

    async def read_header(self, key: str) -> Session | None:
        """Read an existing header without loading history or recreating deleted state."""

        def read():
            session = self.repository.load(key, history=False)
            return (
                replace(
                    session,
                    _baseline=None,
                    messages=[],
                    provider_state=None,
                    metadata=deepcopy(session.metadata),
                )
                if session is not None
                else None
            )

        return await self.operations.execute(key, read, write=False, operation_name="read_header")

    async def _get(self, key: str, *, history: bool) -> Session:
        def view(session: Session) -> Session:
            if history:
                self.repository.publish(session)
                return self.repository.draft(session)
            header = replace(
                session,
                _baseline=None,
                messages=[],
                provider_state=None,
                metadata=deepcopy(session.metadata),
            )
            header.last_archived = session.last_archived
            return header

        def read() -> Session | None:
            session = self.repository.load(key, history=history)
            return view(session) if session is not None else None

        def create() -> Session:
            def commit() -> tuple[Session, bool]:
                session = self.repository.load(key, history=history)
                created = session is None
                if session is None:
                    with self.repository.lock:
                        self.repository.retired.discard(key)
                    session = Session(key=key)
                    self.repository.commit(session)
                return session, created

            session, created = self.repository.store.run_write(commit)
            if created and not history:
                self.repository.publish(session)
            return view(session)

        async def get() -> Session:
            session = await self.operations.run(read, write=False)
            if session is None:
                session = await self.operations.run(create, write=True)
            return session

        return await self.operations.submit(
            key, get, operation_name="get" if history else "get_header"
        )

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
        values = deepcopy(dict(metadata))

        def create() -> Session:
            def write() -> Session:
                parent = self.repository.load(parent_key, history=False)
                if parent is None:
                    with self.repository.lock:
                        if parent_key in self.repository.retired:
                            raise SessionConflictError("parent session was deleted")
                    parent = Session(key=parent_key, policy=policy)
                    self.repository.commit(parent)
                effective = SessionPolicy(
                    persist=parent.policy.persist and policy.persist,
                    log_content=parent.policy.log_content and policy.log_content,
                    disabled_tools=parent.policy.disabled_tools | policy.disabled_tools,
                )
                child = Session(key=key, policy=effective, metadata=values)
                child.metadata[PARENT_SESSION_KEY] = parent_key
                child.add_message("user", content)
                self.repository.commit(child)
                return child

            child = self.repository.store.run_write(write)
            self.repository.publish(child)
            return self.repository.draft(child)

        return await self.operations.execute(
            (parent_key, key), create, operation_name="create_child"
        )
