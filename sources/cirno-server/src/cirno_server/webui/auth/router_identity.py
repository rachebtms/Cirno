"""Browser identity operations backed by canonical conversation metadata."""
from cirno_core.bus.outbound_events import SessionUpdatedEvent
from cirno_core.session.keys import ROUTER_CHAT_ID, ROUTER_SESSION_KEY
from cirno_core.session.router_session import ensure_router_session
from cirno_core.session.session_handles import SessionHandleResolver, normalize_session_handle
from cirno_core.session.state.handles import SessionHandleConflictError

from .store import AccountError


class RouterIdentity:
    def __init__(self, sessions, bus):
        self.sessions = sessions
        self.bus = bus

    async def validate_registration(self, name: object) -> None:
        try:
            if not isinstance(name, str):
                raise ValueError("invalid name")
            name = normalize_session_handle(name)
        except ValueError as exc:
            raise AccountError("invalid_router_handle") from exc
        target = await SessionHandleResolver(self.sessions).aresolve(name)
        if target and target.session_key != ROUTER_SESSION_KEY:
            raise AccountError("router_handle_taken", 409)

    async def initialize(self, handle: str, *, registration: bool = False) -> None:
        await ensure_router_session(self.sessions, handle=handle, initialize=registration)

    async def read(self) -> dict[str, str]:
        handle = await SessionHandleResolver(self.sessions).ahandle_for_session(ROUTER_SESSION_KEY)
        if handle is None:
            raise RuntimeError("Router conversation has not been initialized")
        return dict(handle.public_payload())

    async def rename(self, name: object) -> dict[str, str]:
        if not isinstance(name, str):
            raise AccountError("invalid_router_handle")
        try:
            identity = await self.sessions.state.rename_session_handle(ROUTER_SESSION_KEY, name)
        except SessionHandleConflictError as exc:
            raise AccountError("router_handle_taken", 409) from exc
        except ValueError as exc:
            raise AccountError("invalid_router_handle") from exc
        await self.bus.publish_event(SessionUpdatedEvent(scope="metadata"), channel="websocket", chat_id=ROUTER_CHAT_ID)
        return identity
