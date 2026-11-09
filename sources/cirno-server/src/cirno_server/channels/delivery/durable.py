"""Durable delivery receipts and source-session access checks."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from cirno_core.bus.delivery import ChannelNotReadyError, DeliveryRejectedError
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_core.security.workspace_access import WorkspaceScopeResolver
from cirno_core.security.workspace_policy import resolve_allowed_path
from cirno_core.session.manager import SessionManager
from cirno_core.utils.cancellation import shield_and_drain
from loguru import logger

from cirno_server.channels.base import BaseChannel
from cirno_server.channels.delivery.events import send_event
from cirno_server.channels.outbox import DeliveryOutbox, DeliveryStatus

_T = TypeVar("_T")


class DurableDelivery:
    def __init__(
        self,
        bus: MessageBus,
        config_path: Path,
        sessions: SessionManager | None,
        config: Callable[[], Config],
    ) -> None:
        self.bus = bus
        self.config_path = config_path
        self.sessions = sessions
        self.config = config
        self.outbox = DeliveryOutbox(config_path.parent / "state" / "delivery" / "outbox.sqlite3")
        self._io_lock = asyncio.Lock()
        bus.outbound_recorder = self.record

    async def _io(self, operation: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        # The outbox has one runtime owner. Serialize its initialization and
        # writes, and retain the lock until an accepted worker has settled.
        async with self._io_lock:
            return await shield_and_drain(asyncio.to_thread(operation, *args, **kwargs))

    def record(self, msg: OutboundMessage) -> Awaitable[None] | None:
        if msg.delivery is None:
            return None
        return self._record(msg)

    async def _record(self, msg: OutboundMessage) -> None:
        with self.bus.admission.activity():
            await self._io(self.outbox.record, msg, deduplicate=bool(msg.metadata.get("_inbox_notice")))

    async def ready(self) -> list[OutboundMessage]:
        return await self._io(self.outbox.ready)

    async def finish(self, msg: OutboundMessage, status: DeliveryStatus, error: str | None = None) -> None:
        await self._io(self.outbox.finish, msg, status, error)

    async def send(self, channel: BaseChannel, msg: OutboundMessage) -> None:
        request = msg.delivery
        if request is not None and request.session_generation is not None and self.sessions:
            session = await self.sessions.state.read_header(request.session_key)
            if session is None or session.generation != request.session_generation:
                await self.finish(msg, "failed", "session_replaced")
                return
            if msg.media:
                # An accepted local path can become a symlink during an outage.
                # Recheck the current source policy before the adapter opens it.
                scope = WorkspaceScopeResolver(
                    self.config().workspace_path,
                    self.config().tools.restrict_to_workspace,
                ).for_turn(
                    channel=request.session_key.split(":", 1)[0],
                    message_metadata={},
                    session_metadata=session.metadata,
                )
                try:
                    for path in msg.media:
                        if not path.startswith(("http://", "https://")):
                            resolve_allowed_path(
                                path,
                                workspace=scope.project_path,
                                allowed_root=scope.project_path
                                if scope.restrict_to_workspace
                                else None,
                                extra_allowed_roots=[self.config_path.parent / "state" / "media"],
                            )
                except (OSError, ValueError):
                    await self.finish(msg, "failed", "attachment_access_denied")
                    return
        claimed = submitted = False

        async def claim() -> bool:
            nonlocal claimed
            claimed = await self._io(self.outbox.claim, msg)
            return claimed

        try:
            if not await shield_and_drain(claim()):
                return
            submitted = True
            await send_event(channel, msg)
        except ChannelNotReadyError:
            # The adapter guarantees that no part of the message was submitted.
            await self.finish(msg, "pending", "channel_not_ready")
        except DeliveryRejectedError:
            await self.finish(msg, "failed", "delivery_rejected")
        except asyncio.CancelledError:
            if claimed:
                await self.finish(msg, "unknown" if submitted else "pending",
                                  "interrupted_send" if submitted else "channel_not_ready")
            raise
        except Exception as error:
            if not submitted:
                raise
            # A timeout can follow an accepted send, including a partial multi-part send.
            # Retrying the whole result here could deliver it twice.
            await self.finish(msg, "unknown", type(error).__name__)
            logger.exception("Durable delivery {} has an unknown transport result", msg.delivery_id)
        else:
            await self.finish(msg, "sent")
