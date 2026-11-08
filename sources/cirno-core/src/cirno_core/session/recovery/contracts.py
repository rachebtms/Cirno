"""Conversation recovery contracts ownership."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, Protocol, TypedDict, cast

from cirno_core.bus.events import InboundMessage

RUNTIME_CHECKPOINT_KEY = "runtime_checkpoint"


PENDING_USER_TURN_KEY = "pending_user_turn"


REQUEST_ORIGIN_METADATA_KEY = "request_origin"


RECOVERY_METADATA_KEY = "webui_recovery"


RECOVERY_INBOUND_METADATA_KEY = "_webui_recovery_id"


PENDING_FOLLOWUPS_KEY = "pending_user_followups"


PENDING_FOLLOWUP_ID_KEY = "_recovery_followup_id"


TURN_STATE_METADATA_KEYS = frozenset(
    {
        PENDING_USER_TURN_KEY,
        RUNTIME_CHECKPOINT_KEY,
        PENDING_FOLLOWUPS_KEY,
    }
)


PROVIDER_STATE_CHECKPOINT_VERSION_KEY = "provider_state_checkpoint_version"


PROVIDER_STATE_CHECKPOINT_VERSION = "v1"


UNCERTAIN_TOOL_PHASES = frozenset({"awaiting_tools"})


KNOWN_CHECKPOINT_PHASES = frozenset(
    {"final_response", "tools_completed", "awaiting_tools", "error"}
)


class RequestOrigin(TypedDict):
    message_id: str | None
    turn_id: str


def request_origin_from_metadata(metadata: Mapping[str, Any]) -> RequestOrigin | None:
    """Read the request identity carried by continuation or recovery metadata."""
    value = metadata.get(REQUEST_ORIGIN_METADATA_KEY)
    if not isinstance(value, dict):
        return None
    origin = cast(dict[str, object], value)
    message_id = origin.get("message_id")
    turn_id = origin.get("turn_id")
    if message_id is not None and not isinstance(message_id, str):
        return None
    if not isinstance(turn_id, str) or not turn_id:
        return None
    return {"message_id": message_id, "turn_id": turn_id}


class RecoveryAdmission(Protocol):
    """Narrow AgentLoop boundary for explicit recovery validation."""

    async def admit(self, message: InboundMessage) -> bool: ...

    async def turn_stopped(self, session_key: str) -> None: ...

    async def resume_session(self, session_key: str) -> dict[str, Any]: ...

    def register_recovery_task(self, session_key: str, task: asyncio.Task[Any]) -> None: ...

    def unregister_recovery_task(self, session_key: str, task: asyncio.Task[Any]) -> None: ...


class RecoveryActionError(ValueError):
    """A stale or malformed recovery action from an authenticated WebUI."""

    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status
