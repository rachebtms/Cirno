"""Private child sessions for subagent transcripts and task observations."""

from __future__ import annotations

import math
import time
from typing import Any, cast

from loguru import logger
from pydantic import TypeAdapter, ValidationError

from cirno_core.agent.subagents.status import SubagentSessionError as SubagentSessionError
from cirno_core.agent.subagents.status import SubagentStatus
from cirno_core.session.manager import SessionManager
from cirno_core.session.model import Session, SessionPolicy
from cirno_core.session.sqlite_store import SessionConflictError
from cirno_core.session.types import (
    CHILD_SESSION_GENERATION_REQUIRED_KEY,
    PARENT_SESSION_GENERATION_KEY,
    PARENT_SESSION_KEY,
    SESSION_TYPE_KEY,
    SessionType,
)

SUBAGENT = SessionType("subagent", needs_handle=False, public_history=False)
TASK_METADATA_KEY = "subagent_task"
_STATUS = TypeAdapter(SubagentStatus)
_ACTIVE_STATES = {"queued", "running", "stopping"}


class SubagentSessions:
    """Use the common session store; keep task access owned by the parent."""

    def __init__(self, sessions: SessionManager):
        self.sessions = sessions
        sessions.types.register(SUBAGENT)

    @staticmethod
    def key(task_id: str) -> str:
        return f"subagent:{task_id}"

    def exists(self, owner: str) -> bool:
        return (
            self.sessions.get_cached_metadata(owner, include_runtime=False) is not None
            or self.sessions.read_session_metadata(owner, include_runtime=False) is not None
        )

    def contains(self, task_id: str, owner: str, *, child_generation: str | None = None) -> bool:
        key = self.key(task_id)
        metadata = self.sessions.get_cached_metadata(key, include_runtime=False)
        if metadata is None:
            metadata = (self.sessions.read_session_metadata(key, include_runtime=False) or {}).get("metadata", {})
        return self._belongs_to(metadata, owner) and (
            child_generation is None or child_generation == self._generation(task_id)
        )

    def _generation(self, task_id: str) -> str | None:
        key = self.key(task_id)
        identity = self.sessions.state.peek_identity(key)
        if identity is not None and not identity.policy.persist:
            return identity.generation
        version = self.sessions.read_session_version(key)
        return version[0] if version is not None else None

    def _belongs_to(self, metadata: dict[str, Any], owner: str) -> bool:
        if metadata.get(SESSION_TYPE_KEY) != SUBAGENT.name or metadata.get(PARENT_SESSION_KEY) != owner:
            return False
        generation = metadata.get(PARENT_SESSION_GENERATION_KEY)
        # Historical children remain readable until their parent is replaced.
        # A replacement revokes unbound children without rewriting old records.
        if generation is None:
            parent = self.sessions.get_cached_metadata(owner, include_runtime=False)
            if parent is None:
                parent = (self.sessions.read_session_metadata(owner, include_runtime=False) or {}).get("metadata")
            return parent is not None and parent.get(CHILD_SESSION_GENERATION_REQUIRED_KEY) is not True
        identity = self.sessions.state.peek_identity(owner)
        if identity is not None and not identity.policy.persist:
            return generation == identity.generation
        version = self.sessions.read_session_version(owner)
        return version is not None and generation == version[0]

    def snapshot(self, task_id: str, owner: str, *, child_generation: str | None = None) -> Session | None:
        """Read a detached child only while its parent still owns it."""
        if not self.exists(owner) or not self.contains(task_id, owner, child_generation=child_generation):
            return None
        child = self.sessions.get_existing(self.key(task_id))
        if child is not None and child_generation is not None and child.generation != child_generation:
            return None
        return child

    @staticmethod
    def _payload(status: SubagentStatus) -> dict[str, Any]:
        return {
            **_STATUS.dump_python(status, mode="json", exclude={"started_at", "finished_at", "child_generation"}),
            "elapsed_seconds": status.as_dict()["elapsed_seconds"],
        }

    async def create(self, status: SubagentStatus, *, policy: SessionPolicy | None = None) -> Session:
        child = await self.sessions.state.create_child(
            status.owner, self.key(status.task_id),
            metadata={SESSION_TYPE_KEY: SUBAGENT.name, TASK_METADATA_KEY: self._payload(status)},
            content=status.task_description, policy=policy or SessionPolicy(),
        )
        status.child_generation = child.generation
        return child

    async def save(self, status: SubagentStatus) -> bool:
        if status.child_generation is None:
            return False
        try:
            await self.sessions.state.update_metadata(
                self.key(status.task_id), {TASK_METADATA_KEY: self._payload(status)},
                expected_generation=status.child_generation,
            )
        except SessionConflictError:
            return False
        return True

    def status(self, task_id: str, owner: str) -> SubagentStatus | None:
        generation = self._generation(task_id)
        if generation is None:
            return None
        payload = self.sessions.read_session_metadata(self.key(task_id), include_runtime=False)
        if payload is None:
            metadata = self.sessions.get_cached_metadata(self.key(task_id), include_runtime=False)
            payload = {"metadata": metadata} if metadata is not None else None
        if payload is None:
            return None
        metadata = payload.get("metadata", {})
        status = self._status_from_metadata(task_id, owner, metadata)
        if status is not None:
            status.child_generation = generation
        return status

    def _status_from_metadata(
        self, task_id: str, owner: str, metadata: dict[str, Any],
    ) -> SubagentStatus | None:
        if not self._belongs_to(metadata, owner):
            return None
        raw: object = metadata.get(TASK_METADATA_KEY)
        if not isinstance(raw, dict):
            raise SubagentSessionError("invalid task session metadata")
        value = cast(dict[str, object], raw)
        elapsed = value.get("elapsed_seconds")
        if (not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool)
                or not math.isfinite(elapsed) or elapsed < 0):
            raise SubagentSessionError("invalid task duration")
        now = time.monotonic()
        try:
            status = _STATUS.validate_python({
                **value, "started_at": now - elapsed,
                "finished_at": now if value.get("completed_at") is not None else None,
            })
        except ValidationError as exc:
            raise SubagentSessionError("invalid task session metadata") from exc
        if status.owner != owner or status.task_id != task_id:
            raise SubagentSessionError("invalid task ownership")
        return status

    def load(self, owner: str) -> dict[str, SubagentStatus]:
        result: dict[str, SubagentStatus] = {}
        for row in self.sessions.list_child_session_metadata(owner):
            key = row["key"]
            task_id = key.removeprefix("subagent:")
            if key != self.key(task_id):
                continue
            status = self._status_from_metadata(task_id, owner, row["metadata"])
            if status is not None:
                result[task_id] = status
        return result

    async def interrupt_pending(self) -> None:
        """Seal abandoned work after the gateway acquires execution ownership."""
        for row in self.sessions.list_sessions():
            key = row["key"]
            payload = self.sessions.read_session_metadata(key, include_runtime=False)
            metadata = (payload or {}).get("metadata", {})
            if metadata.get(SESSION_TYPE_KEY) != SUBAGENT.name:
                continue
            owner = metadata.get(PARENT_SESSION_KEY)
            if not isinstance(owner, str):
                continue
            try:
                status = self.status(key.removeprefix("subagent:"), owner)
                if status is None or status.state not in _ACTIVE_STATES:
                    continue
                status.state = status.phase = "interrupted"
                status.revision += 1
                status.stop_reason = "host_restarted"
                status.finished_at = time.monotonic()
                status.completed_at = time.time()
                status.partial = bool(status.result)
                status.tool_events = []
                status.receipts = {key: "undelivered" if receipt == "accepted" else receipt
                                   for key, receipt in status.receipts.items()}
                await self.save(status)
            except (OSError, SubagentSessionError):
                logger.exception("Could not recover subagent session {}", key)
