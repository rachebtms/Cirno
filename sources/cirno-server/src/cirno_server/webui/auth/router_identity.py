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
        if registration:
            import asyncio
            from cirno_core.profiles.awakening import initialize_awakening
            await asyncio.to_thread(initialize_awakening)

    async def wake(self, language: str) -> bool:
        """Journal the owner's one-time wake request before scheduling execution."""
        import asyncio
        from cirno_core.bus.events import InboundMessage
        from cirno_core.profiles.awakening import awakening_prompt
        from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY

        if not await asyncio.to_thread(awakening_prompt):
            return False
        header = await self.sessions.state.read_header(ROUTER_SESSION_KEY)
        if header is None:
            raise RuntimeError("Router conversation has not been initialized")
        if header.metadata.get("awakening_started"):
            return False
        self.bus.admission.check()
        message = InboundMessage(
            channel="websocket", sender_id="system:awakening", chat_id=ROUTER_CHAT_ID,
            input_role="system", require_existing_session=True,
            session_key_override=ROUTER_SESSION_KEY, session_generation=header.generation,
            content=f"The owner chose to wake their assistant after setup. Begin the first introduction in language {language}. Follow Home BOOTSTRAP.md; do not invent user preferences.",
            metadata={PENDING_FOLLOWUP_ID_KEY: "first-awakening", "_awakening": True},
        )
        await self.sessions.state.queue_followup(ROUTER_SESSION_KEY, message)
        await self.sessions.state.update_metadata(ROUTER_SESSION_KEY, {"awakening_started": True})
        await self.bus.publish_inbound(message)
        return True

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
