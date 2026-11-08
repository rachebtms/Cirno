"""Session storage location and synchronous administrative operations."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, TypeVar, cast

from cirno_core.session.branching import fork_session
from cirno_core.session.contracts import MessageProjection, SessionMetadataPayload
from cirno_core.session.display_history import HistoryFact, HistoryReader
from cirno_core.session.location import SessionLocation
from cirno_core.session.model import Session
from cirno_core.session.types import SessionTypes

if TYPE_CHECKING:
    from cirno_core.projects.service import Projects
    from cirno_core.session.state import SessionState

_T = TypeVar("_T")
SESSION_CACHE_MAX_SIZE = 128


class SessionManager:
    """Locate session storage and expose synchronous administrative operations."""

    def __init__(
        self,
        workspace: Path,
        *,
        sessions_root: Path | None = None,
    ):
        from cirno_core.session.sqlite_store import SqliteSessionStore

        self.workspace = workspace
        self.location = SessionLocation(workspace, sessions_root=sessions_root)
        self.sessions_dir = self.location.sessions_dir
        self._store = SqliteSessionStore(self.sessions_dir)
        self._store.initialize()
        self._delete_observer: Callable[[str], None] | None = None
        self.types = SessionTypes()
        self._state: SessionState | None = None
        self._projects: Projects | None = None

    @property
    def projects(self) -> Projects:
        """One project mutation owner shared by Web UI and conversation tools."""
        if self._projects is None:
            from cirno_core.projects.service import Projects

            self._projects = Projects(self)
        return self._projects

    @property
    def state(self) -> SessionState:
        """The asynchronous owner of session state transitions."""
        if self._state is None:
            from cirno_core.session.state import SessionState

            self._state = SessionState(self._store, on_delete=self._notify_delete, types=self.types)
        return self._state

    def _notify_delete(self, key: str) -> None:
        if self._delete_observer is not None:
            self._delete_observer(key)

    def get_cached(self, key: str) -> Session | None:
        return self.state.peek(key)

    def get_cached_metadata(self, key: str, *, include_runtime: bool = True) -> dict[str, Any] | None:
        """Return detached committed metadata without copying conversation history."""
        return self._state.peek_metadata(key, include_runtime=include_runtime) if self._state is not None else None

    def set_delete_observer(self, observer: Callable[[str], None]) -> None:
        """Observe explicit session deletion for process-local state cleanup."""
        self._delete_observer = observer

    def _require_offline_mutation(self) -> None:
        if self._state is not None and self._state.is_bound:
            raise RuntimeError(
                "synchronous session mutation is unavailable after the async owner starts"
            )

    def get_or_create(self, key: str) -> Session:
        """Load a detached snapshot for synchronous administrative callers."""
        return self._store.load(key) or Session(key=key)

    def get_existing(self, key: str) -> Session | None:
        """Read an existing session without recreating a deleted conversation."""
        return self.get_cached(key) or self._store.load(key)

    def child_session_keys(self, parent_key: str) -> list[str]:
        """Find persisted children through their declared parent."""
        return self._store.child_session_keys(parent_key)

    def list_child_session_metadata(self, parent_key: str) -> list[SessionMetadataPayload]:
        """Read persisted child headers without transcripts, checkpoints, or pending inputs."""
        return self._store.list_child_session_metadata(parent_key)

    def save(self, session: Session) -> None:
        """Commit an offline administrative snapshot, rejecting obsolete history."""
        self._require_offline_mutation()
        if session.policy.persist:
            self._store.save(session)


    def invalidate(self, key: str) -> None:
        if self._state is not None:
            self._state.forget_transient(key)

    def delete_session(self, key: str) -> bool:
        """Delete a session and its persisted descendants in one transaction."""
        self._require_offline_mutation()
        def delete() -> bool:
            pending = [key]
            collected: set[str] = set()
            while pending:
                current = pending.pop()
                if current in collected:
                    continue
                collected.add(current)
                pending.extend(self.child_session_keys(current))
            deleted = False
            for current in collected:
                deleted = self._store.delete(current) or deleted
                self.invalidate(current)
                self._notify_delete(current)
            return deleted

        return self._store.run_write(delete)

    def fork_session_before_user_index(
        self, source_key: str, target_key: str, before_user_index: int,
    ) -> Session | None:
        self._require_offline_mutation()

        def fork() -> Session | None:
            source = self._store.load(source_key)
            if source is None:
                return None
            context_index = self._store.fork_context_index(source, before_user_index)
            if context_index is None:
                return None
            target = fork_session(source, target_key, context_index)
            if target is not None:
                self._store.save(target)
                self._store.copy_history_prefix(source_key, target, before_user_index)
            return target

        return self._store.run_write(fork)

    def project_messages(self, key: str, project: MessageProjection[_T]) -> _T | None:
        """Project complete canonical history inside one storage snapshot."""
        return self._store.project_messages(key, project)

    def project_history(self, key: str, project: Callable[[HistoryReader], _T]) -> _T:
        """Read an administrative display snapshot; runtime uses state.project_history."""
        return self._store.project_history(key, project)

    def append_history(self, key: str, facts: list[HistoryFact]) -> None:
        """Append offline fixture/import facts with the current admitted generation."""
        self._require_offline_mutation()

        def append() -> None:
            session = self._store.load(key, history=False)
            if session is None:
                session = self.get_or_create(key)
                self._store.save(session)
            self._store.append_history(key, facts, expected_generation=session.generation)
        self._store.run_write(append)

    def read_session_file(self, key: str) -> dict[str, Any] | None:
        """Read a session without populating the cache."""
        return cast(dict[str, Any] | None, self._store.read(key))

    def read_session_snapshot(self, key: str) -> Session | None:
        """Load a detached session snapshot without populating the runtime cache."""
        return self._store.load(key)

    def read_session_version(self, key: str) -> tuple[str, int] | None:
        """Return a cheap committed version, including delete/recreate identity."""
        return self._store.read_version(key)

    def read_session_metadata(self, key: str, *, include_runtime: bool = True) -> dict[str, Any] | None:
        """Read session metadata without loading the transcript."""
        return cast(dict[str, Any] | None, self._store.read_metadata(key, include_runtime=include_runtime))

    def ensure_session_handles_offline(self) -> dict[str, str]:
        """Allocate missing handles during offline administration."""
        from cirno_core.session.session_handles import (
            SESSION_HANDLE_METADATA_KEY,
            allocate_session_handles,
        )

        self._require_offline_mutation()

        def ensure() -> dict[str, str]:
            names, updates = allocate_session_handles(self._store.list_metadata(), self.types)
            for key, name in updates.items():
                self._store.update_metadata(key, {SESSION_HANDLE_METADATA_KEY: name})
            return names

        return self._store.run_write(ensure)

    def update_session_metadata(
        self,
        key: str,
        updates: dict[str, Any],
    ) -> bool:
        """Atomically update metadata while the async owner is not running."""
        self._require_offline_mutation()
        return self._store.update_metadata(key, updates)

    def list_session_metadata(self) -> list[dict[str, Any]]:
        return self._store.list_metadata()

    def list_sessions(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._store.list_sessions())
