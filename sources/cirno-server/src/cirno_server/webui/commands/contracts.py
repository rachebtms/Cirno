"""Shared transport capabilities and mutation operation results."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Protocol, TypeGuard

from websockets.asyncio.server import ServerConnection


def is_request_id(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value) is not None


@dataclass(frozen=True)
class WebUIRequestResult:
    result: Any = None
    status: int | None = None
    message: str | None = None


@dataclass
class WebUIRequestOperation:
    action: str
    payload_digest: bytes
    task: asyncio.Task[WebUIRequestResult]
    completed_at: float | None = None


class WebUICommandTransport(Protocol):
    """Typed transport capabilities consumed by WebUI command orchestration."""

    def is_allowed(self, sender_id: str) -> bool: ...

    def webui_subscribers(self, chat_id: str) -> tuple[ServerConnection, ...]: ...

    def webui_connection_chats(self, connection: ServerConnection) -> tuple[str, ...]: ...

    def webui_attach(self, connection: ServerConnection, chat_id: str) -> None: ...

    def webui_detach(self, connection: ServerConnection, chat_id: str) -> None: ...

    def webui_clear_connection_default(self, connection: ServerConnection) -> None: ...

    async def webui_send_event(
        self,
        connection: ServerConnection,
        event: str,
        **fields: Any,
    ) -> None: ...

    async def webui_send_raw(
        self,
        connection: ServerConnection,
        raw: str,
        *,
        label: str = "",
    ) -> None: ...

    async def webui_dispatch_message(
        self,
        *,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None,
        metadata: dict[str, Any],
        session_key: str | None,
        require_existing_session: bool,
        session_generation: str | None,
    ) -> None: ...


class BroadcastWebUIEvent(Protocol):
    async def __call__(self, event: str, **fields: Any) -> None: ...
