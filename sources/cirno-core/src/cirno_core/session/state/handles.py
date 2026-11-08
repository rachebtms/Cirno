"""Stable conversation identities and mutable, unique display handles."""
from __future__ import annotations

from dataclasses import dataclass

from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.sqlite_store import SessionConflictError

from .operations import SessionOperations
from .repository import SessionRepository


class SessionHandleConflictError(ValueError):
    """Another conversation already owns the requested display name."""


@dataclass
class SessionHandles:
    repository: SessionRepository
    operations: SessionOperations

    async def ensure_session_handles(self) -> dict[str, str]:
        """Allocate stable public handles through the runtime mutation owner."""
        from cirno_core.session.session_handles import (
            SESSION_HANDLE_METADATA_KEY,
            allocate_session_handles,
        )

        def read() -> tuple[dict[str, str], dict[str, str]]:
            return self.repository.store.run_read(
                lambda: allocate_session_handles(
                    self.repository.store.list_metadata(), self.repository.types
                ),
            )

        def allocate() -> dict[str, str]:
            changed: list[str] = []

            def write() -> dict[str, str]:
                names, updates = allocate_session_handles(
                    self.repository.store.list_metadata(), self.repository.types
                )
                for key, name in updates.items():
                    if self.repository.store.update_display_metadata(
                        key,
                        {SESSION_HANDLE_METADATA_KEY: name},
                    ):
                        changed.append(key)
                return names

            names = self.repository.store.run_write(write)
            with self.repository.lock:
                for key in changed:
                    self.repository.snapshots.pop(key, None)
            return names

        async def ensure() -> dict[str, str]:
            names, updates = await self.operations.run(read, write=False)
            if updates:
                # Another process may allocate or delete after our read snapshot.
                # Recompute the full allocation under the cross-process write lock.
                names = await self.operations.run(allocate, write=True)
            return names

        return await self.operations.submit(None, ensure, operation_name="ensure_session_handles")

    async def rename(self, key: str, name: str) -> dict[str, str]:
        from cirno_core.session.session_handles import (
            SESSION_HANDLE_METADATA_KEY, normalize_session_handle, session_handle_for_name,
        )
        normalized = normalize_session_handle(name)

        def rename() -> dict[str, str]:
            def write() -> dict[str, str]:
                rows = self.repository.store.list_metadata()
                target = next((row for row in rows if row["key"] == key), None)
                if target is None or not self.repository.types.needs_handle(target["metadata"]):
                    raise SessionConflictError("conversation does not exist")
                for row in rows:
                    if row["key"] != key and row["metadata"].get(SESSION_HANDLE_METADATA_KEY) == normalized:
                        raise SessionHandleConflictError("conversation name is already in use")
                values = {SESSION_HANDLE_METADATA_KEY: normalized}
                if key == ROUTER_SESSION_KEY:
                    values["title"] = f"@{normalized}"
                self.repository.store.update_display_metadata(key, values)
                return dict(session_handle_for_name(key, normalized).public_payload())

            result = self.repository.store.run_write(write)
            with self.repository.lock:
                self.repository.snapshots.pop(key, None)
            return result

        # A global barrier orders allocation and rename, including concurrent owners.
        # The SQL write transaction checks uniqueness before changing any metadata.
        return await self.operations.execute(None, rename, operation_name="rename_session_handle")
