"""WebSocket server channel: cirno acts as a WebSocket server and serves connected clients."""

from __future__ import annotations

import asyncio
import errno
import json
import socket
import ssl
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.runtime.admission import RuntimeMaintenanceError
from websockets.asyncio.server import Server, ServerConnection, serve, unix_serve
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response as WsResponse
from websockets.protocol import CONNECTING

from cirno_server.channels.base import BaseChannel
from cirno_server.channels.websocket.binary_http import BinaryHTTPBridge
from cirno_server.channels.websocket.config import WebSocketConfig
from cirno_server.channels.websocket.writers import ConnectionWriters
from cirno_server.webui.commands.router import WebUICommandRouter
from cirno_server.webui.http_utils import (
    normalize_config_path as _normalize_config_path,
)
from cirno_server.webui.http_utils import (
    parse_request_path as _parse_request_path,
)
from cirno_server.webui.http_utils import (
    query_first as _query_first,
)
from cirno_server.webui.outbound_delivery import ChatAudience, WebUIAudience, WebUIOutboundDelivery
from cirno_server.webui.services import ServerServices
from cirno_server.webui.websocket_logging import websockets_server_logger

# Plain HTTP WebUI routes also run through websockets.process_request.
_WEBUI_HTTP_OPEN_TIMEOUT_S = 360.0
_LISTENER_CHECK_INTERVAL_S = 0.5
_LISTENER_STABLE_AFTER_S = 30.0
_LISTENER_RESTART_BACKOFF_S = (1.0, 2.0, 4.0, 8.0, 16.0, 30.0)

# A bind conflict or invalid address needs operator action and must not be
# retried forever. These errors can be caused by a transient local network
# interruption and are safe to retry at the channel boundary.
_RECOVERABLE_LISTENER_ERRNOS = {
    getattr(socket, name)
    for name in (
        "ECONNABORTED",
        "ECONNRESET",
        "EHOSTDOWN",
        "EHOSTUNREACH",
        "ENETDOWN",
        "ENETRESET",
        "ENETUNREACH",
        "ETIMEDOUT",
    )
    if hasattr(socket, name)
}
_RECOVERABLE_LISTENER_WINERRORS = {
    64,  # ERROR_NETNAME_DELETED / "The specified network name is no longer available."
    995,  # ERROR_OPERATION_ABORTED
    10050,  # WSAENETDOWN
    10052,  # WSAENETRESET
    10053,  # WSAECONNABORTED
    10054,  # WSAECONNRESET
    10060,  # WSAETIMEDOUT
    10065,  # WSAEHOSTUNREACH
}


def _parse_envelope(raw: str) -> dict[str, Any] | None:
    """Return a typed envelope dict if the frame is a new-style JSON envelope, else None.

    A frame qualifies when it parses as a JSON object with a string ``type`` field.
    Untyped or malformed frames return None and are rejected by the caller.
    """
    text = raw.strip()
    if not text.startswith("{"):
        return None
    try:
        data = cast(object, json.loads(text))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    envelope = cast(dict[str, Any], data)
    t = envelope.get("type")
    if not isinstance(t, str):
        return None
    return envelope


class _ListenerUnavailableError(OSError):
    """Raised when a previously bound listener loses its serving socket."""


class WebSocketChannel(BaseChannel):
    """Run a local WebSocket server; forward text/JSON messages to the message bus."""

    name = "websocket"
    display_name = "WebSocket"

    def __init__(
        self,
        config: Any,
        bus: MessageBus,
        *,
        gateway: ServerServices,
    ):
        if isinstance(config, dict):
            config = WebSocketConfig.model_validate(config)
        super().__init__(config, bus)
        self.config: WebSocketConfig = config
        # chat_id -> connections subscribed to it (fan-out target).
        self._subs: dict[str, set[ServerConnection]] = {}
        # connection -> chat_ids it is subscribed to (O(1) cleanup on disconnect).
        self._conn_chats: dict[ServerConnection, set[str]] = {}
        # connection -> chat_id selected when establishing the connection.
        self._conn_default: dict[ServerConnection, str] = {}
        # Connections authenticated with a one-time token from /v0/bootstrap.
        self._webui_connections = gateway.endpoint.webui_connections
        self._stop_event: asyncio.Event | None = None
        self._server_task: asyncio.Task[None] | None = None
        self._server: Server | None = None
        self.writers = ConnectionWriters(self._cleanup_connection, self.logger)

        self.gateway = gateway
        self._uploads = gateway.uploads
        from cirno_server.backup.http import BackupHTTP
        self._backups = BackupHTTP(gateway.settings.config.path, self._uploads, bus, gateway.session_manager, maintenance=gateway.maintenance)
        from cirno_server.webui.media.http import MediaHTTP
        self._media_http = MediaHTTP(gateway.media, gateway.workspaces.existing_scope_for_session_key)
        self._outbound = WebUIOutboundDelivery(
            self,
            media=gateway.media,
            transcripts=gateway.transcripts,
            temporary_chats=gateway.temporary_chats,
            session_projection=gateway.session_projection,
        )
        self._commands = WebUICommandRouter(self, gateway, outbound=self._outbound)

    # -- Subscription bookkeeping -------------------------------------------

    def webui_subscribers(self, chat_id: str) -> tuple[ServerConnection, ...]:
        """Return a stable snapshot of one chat's transport subscribers."""
        return tuple(self._subs.get(chat_id, ()))

    def webui_recipients(self, audience: WebUIAudience) -> tuple[ServerConnection, ...]:
        """Snapshot the selected audience without interpreting its public frames."""
        if isinstance(audience, ChatAudience):
            return self.webui_subscribers(audience.chat_id)
        if audience == "authenticated_webui":
            return tuple(self._webui_connections)
        return tuple(self._conn_chats)

    def webui_connection_chats(self, connection: ServerConnection) -> tuple[str, ...]:
        return tuple(self._conn_chats.get(connection, ()))

    def webui_attach(self, connection: ServerConnection, chat_id: str) -> None:
        self._attach(connection, chat_id)

    def webui_detach(self, connection: ServerConnection, chat_id: str) -> None:
        self._detach(connection, chat_id)

    def webui_clear_connection_default(self, connection: ServerConnection) -> None:
        self._conn_default.pop(connection, None)

    async def webui_send_event(
        self,
        connection: ServerConnection,
        event: str,
        **fields: Any,
    ) -> None:
        await self._send_event(connection, event, **fields)

    async def webui_send_raw(
        self,
        connection: ServerConnection,
        raw: str,
        *,
        label: str = "",
    ) -> None:
        await self.writers.send(connection, raw, label=label)

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
    ) -> None:
        await self._handle_message(
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
            media=media,
            metadata=metadata,
            session_key=session_key,
            require_existing_session=require_existing_session,
            session_generation=session_generation,
        )

    def _attach(self, connection: ServerConnection, chat_id: str) -> None:
        """Idempotently subscribe *connection* to *chat_id*."""
        if not self.writers.register(connection):
            return
        self._subs.setdefault(chat_id, set()).add(connection)
        self._conn_chats.setdefault(connection, set()).add(chat_id)


    def _detach(self, connection: ServerConnection, chat_id: str) -> None:
        chats = self._conn_chats.get(connection)
        if chats is not None:
            chats.discard(chat_id)
            if not chats:
                self._conn_chats.pop(connection, None)
        subscribers = self._subs.get(chat_id)
        if subscribers is not None:
            subscribers.discard(connection)
            if not subscribers:
                self._subs.pop(chat_id, None)

    async def _cleanup_connection(self, connection: ServerConnection) -> None:
        """Remove *connection* from every subscription set; safe to call multiple times."""
        self._uploads.revoke(connection)
        state = await self.writers.begin_cleanup(connection)
        try:
            await self._commands.cleanup_connection(connection)
        finally:
            for chat_id in tuple(self._conn_chats.get(connection, ())):
                self._detach(connection, chat_id)
            self._conn_default.pop(connection, None)
            self.gateway.endpoint.discard_connection(connection)
            self.writers.finish_cleanup(connection, state)

    async def _send_event(
        self,
        connection: ServerConnection,
        event: str,
        **fields: Any,
    ) -> None:
        """Send a control event (attached, error, ...) to a single connection."""
        payload: dict[str, Any] = {"event": event}
        payload.update(fields)
        raw = json.dumps(payload, ensure_ascii=False)
        await self.writers.send(connection, raw, label=f" {event} ")

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return WebSocketConfig().model_dump(by_alias=True)

    def _build_ssl_context(self) -> ssl.SSLContext | None:
        cert = self.config.ssl_certfile.strip()
        key = self.config.ssl_keyfile.strip()
        if not cert and not key:
            return None
        if not cert or not key:
            raise ValueError(
                "ssl_certfile and ssl_keyfile must both be set for WSS, or both left empty"
            )
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(certfile=cert, keyfile=key)
        return ctx

    # -- HTTP dispatch ------------------------------------------------------

    async def _dispatch_http(self, connection: ServerConnection, request: WsRequest) -> Any:
        """Compatibility proxy for the externally composed gateway endpoint."""
        return await self.gateway.endpoint.process_request(
            connection,
            request,
            is_allowed=self.is_allowed,
        )

    def _authorize_websocket_handshake(
        self,
        connection: ServerConnection,
        query: dict[str, list[str]],
        headers: Any = None,
    ) -> Any:
        """Compatibility proxy for handshake tests and integrations."""
        return self.gateway.endpoint.authorize_websocket_handshake(
            connection,
            query,
            headers,
        )

    # -- Server lifecycle and connection ingress ---------------------------

    @staticmethod
    def _socket_is_accepting(sock: socket.socket) -> bool:
        """Return whether a bound socket still advertises a listen capability.

        ``SO_ACCEPTCONN`` is not portable: macOS/BSD raise ``OSError`` with
        ``ENOPROTOOPT`` ("Protocol not available") for this option even on a
        perfectly healthy listening socket. Treating that as "not serving"
        makes the listener look permanently degraded, so the caller retries
        forever and the channel never reaches a ready state. When the option
        is unavailable we fall back to the file-descriptor liveness check.
        """
        if sock.fileno() < 0:
            return False
        try:
            return bool(sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN))
        except OSError as exc:
            if exc.errno in (errno.ENOPROTOOPT, errno.EOPNOTSUPP):
                return True
            raise

    @classmethod
    def _listener_is_serving(cls, server: Server) -> bool:
        """Return whether every bound socket still has a live listen capability."""
        try:
            sockets = server.sockets
            return bool(sockets) and server.is_serving() and all(
                cls._socket_is_accepting(sock) for sock in sockets
            )
        except OSError:
            return False

    @staticmethod
    def _is_recoverable_listener_error(error: Exception, *, was_serving: bool) -> bool:
        if isinstance(error, _ListenerUnavailableError):
            return True
        if not isinstance(error, OSError):
            return False
        if was_serving:
            return True
        winerror = getattr(error, "winerror", None)
        return (
            error.errno in _RECOVERABLE_LISTENER_ERRNOS
            or winerror in _RECOVERABLE_LISTENER_WINERRORS
        )

    async def _wait_for_listener_loss(self, server: Server) -> None:
        """Wait for shutdown or raise when the serving socket disappears."""
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=_LISTENER_CHECK_INTERVAL_S,
                )
            except TimeoutError:
                if not self._listener_is_serving(server):
                    raise _ListenerUnavailableError(
                        "WebSocket listener is no longer accepting connections"
                    )

    async def _close_server(
        self, server: Server, socket_path: str, bridge: BinaryHTTPBridge,
    ) -> None:
        server.close()
        try:
            await bridge.shutdown()
            await server.wait_closed()
        except OSError as exc:
            self.logger.warning("WebSocket server close failed: {}", exc)
        if socket_path:
            with suppress(FileNotFoundError):
                Path(socket_path).unlink()

    def _log_listener_ready(self, scheme: str) -> None:
        self.logger.info(
            "WebSocket server listening on {}",
            (
                f"unix:{self.config.unix_socket_path}{self.config.path}"
                if self.config.unix_socket_path
                else f"{scheme}://{self.config.host}:{self.config.port}{self.config.path}"
            ),
        )
        if self.config.token_issue_path:
            self.logger.info(
                "WebSocket token issue route: {}",
                (
                    f"unix:{self.config.unix_socket_path}"
                    f"{_normalize_config_path(self.config.token_issue_path)}"
                    if self.config.unix_socket_path
                    else (
                        f"{scheme}://{self.config.host}:{self.config.port}"
                        f"{_normalize_config_path(self.config.token_issue_path)}"
                    )
                ),
            )

    async def start(self) -> None:
        from cirno_core.utils.logging_bridge import redirect_lib_logging

        redirect_lib_logging("websockets", level="WARNING")
        ws_logger = websockets_server_logger()

        stop_event = asyncio.Event()
        self._stop_event = stop_event

        ssl_context = self._build_ssl_context()
        scheme = "wss" if ssl_context else "ws"

        async def process_request(
            connection: ServerConnection,
            request: WsRequest,
        ) -> Any:
            return await self._dispatch_http(connection, request)

        def process_response(
            connection: ServerConnection, _request: WsRequest, response: WsResponse,
        ) -> WsResponse:
            # Stay synchronous: websockets sends immediately after this hook returns.
            if connection.state is not CONNECTING:
                exc = connection.protocol.handshake_exc
                if exc is not None:
                    connection.logger.error(
                        "opening handshake failed", exc_info=(type(exc), exc, exc.__traceback__),
                    )
                # The request callback finished; cancel only this connection's handshake.
                raise asyncio.CancelledError("Peer disconnected before handshake response")
            return response

        async def handler(connection: ServerConnection) -> None:
            await self._connection_loop(connection)

        from aiohttp import web

        async def handle_binary(request: web.BaseRequest) -> web.StreamResponse:
            try:
                if request.path.startswith("/v0/backups/"):
                    return await self._backups.handle(request)
                with self.bus.admission.activity():
                    if request.path.startswith("/v0/media/"):
                        return await self._media_http.handle(request)
                    if request.path.startswith("/v0/auth/"):
                        response = await self.gateway.http.auth.handle(request)
                        if request.path == "/v0/auth/change-password" and response.status == 200:
                            self.gateway.tokens.clear()
                            await asyncio.gather(*(connection.close(code=4001, reason="Account password changed")
                                                   for connection in tuple(self._webui_connections)))
                        elif request.path == "/v0/auth/logout" and response.status == 200:
                            session = self.gateway.http.auth.cookie(request.headers)
                            if session:
                                self.gateway.tokens.revoke_browser_session(session)
                                connections = tuple(connection for connection, owner in self.gateway.endpoint.browser_sessions.items()
                                                    if owner == session)
                                await asyncio.gather(*(connection.close(code=4001, reason="Signed out") for connection in connections))
                        return response
                    return await self._uploads.handle(request)
            except RuntimeMaintenanceError:
                response = web.json_response({"error": "Server update is being verified"}, status=503)
                response.force_close()
                return response

        async def prune_uploads() -> None:
            while not stop_event.is_set():
                self._uploads.store.prune()
                self._backups.prune()
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=30)
                except TimeoutError:
                    pass

        prune_task = asyncio.create_task(prune_uploads())

        async def runner() -> None:
            socket_path = self.config.unix_socket_path
            failures = 0
            while not stop_event.is_set():
                server: Server | None = None
                bridge = BinaryHTTPBridge(handle_binary)
                was_serving = False
                started_at = 0.0
                try:
                    if socket_path:
                        path_obj = Path(socket_path)
                        path_obj.parent.mkdir(parents=True, exist_ok=True)
                        with suppress(FileNotFoundError):
                            path_obj.unlink()
                        server = await unix_serve(
                            handler,
                            socket_path,
                            process_request=process_request,
                            process_response=process_response,
                            create_connection=bridge.connection_factory,
                            open_timeout=_WEBUI_HTTP_OPEN_TIMEOUT_S,
                            max_size=self.config.max_message_bytes,
                            ping_interval=self.config.ping_interval_s,
                            ping_timeout=self.config.ping_timeout_s,
                            logger=ws_logger,
                        )
                        with suppress(OSError):
                            path_obj.chmod(0o600)
                    else:
                        server = await serve(
                            handler,
                            self.config.host,
                            self.config.port,
                            process_request=process_request,
                            process_response=process_response,
                            create_connection=bridge.connection_factory,
                            open_timeout=_WEBUI_HTTP_OPEN_TIMEOUT_S,
                            max_size=self.config.max_message_bytes,
                            ping_interval=self.config.ping_interval_s,
                            ping_timeout=self.config.ping_timeout_s,
                            ssl=ssl_context,
                            logger=ws_logger,
                        )

                    self._server = server
                    was_serving = True
                    if not self._listener_is_serving(server):
                        raise _ListenerUnavailableError(
                            "WebSocket listener did not enter a serving state"
                        )
                    self._running = True
                    started_at = asyncio.get_running_loop().time()
                    self._log_listener_ready(scheme)
                    await self._wait_for_listener_loss(server)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._running = False
                    if not self._is_recoverable_listener_error(
                        exc,
                        was_serving=was_serving,
                    ):
                        raise
                    uptime = (
                        asyncio.get_running_loop().time() - started_at
                        if started_at
                        else 0.0
                    )
                    if uptime >= _LISTENER_STABLE_AFTER_S:
                        failures = 0
                    delay = _LISTENER_RESTART_BACKOFF_S[
                        min(failures, len(_LISTENER_RESTART_BACKOFF_S) - 1)
                    ]
                    failures += 1
                    self.logger.warning(
                        "WebSocket listener failed ({}: {}); retrying in {:.1f}s",
                        type(exc).__name__,
                        exc,
                        delay,
                    )
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=delay)
                    except TimeoutError:
                        pass
                finally:
                    self._running = False
                    if server is not None:
                        await self._close_server(server, socket_path, bridge)
                    else:
                        await bridge.shutdown()
                    if self._server is server:
                        self._server = None

        task = asyncio.create_task(runner())
        self._server_task = task
        try:
            await task
        finally:
            prune_task.cancel()
            await asyncio.gather(prune_task, return_exceptions=True)
            self._uploads.store.clear()
            self._running = False
            if self._server_task is task:
                self._server_task = None

    async def _connection_loop(self, connection: ServerConnection) -> None:
        self.writers.accept(connection)
        request = connection.request
        path_part = request.path if request else "/"
        _, query = _parse_request_path(path_part)
        client_id_raw = _query_first(query, "client_id")
        client_id = client_id_raw.strip() if client_id_raw else ""
        if not client_id:
            client_id = f"anon-{uuid.uuid4().hex[:12]}"
        elif len(client_id) > 128:
            self.logger.warning("client_id too long ({} chars), truncating", len(client_id))
            client_id = client_id[:128]

        default_chat_id = str(uuid.uuid4())
        from cirno_server.webui.client_contract import gateway_identity

        try:
            await connection.send(
                json.dumps(
                    {
                        "event": "ready",
                        "chat_id": default_chat_id,
                        "client_id": client_id,
                        **({"upload": self._uploads.issue(connection)}
                           if self.is_allowed(client_id) else {}),
                        **({"terminal": gateway_identity(self.gateway.tokens.instance_id)}
                           if _query_first(query, "terminal_protocol") == "1" else {}),
                    },
                    ensure_ascii=False,
                )
            )
            # Register only after ready is successfully sent to avoid out-of-order sends
            self._conn_default[connection] = default_chat_id
            self._attach(connection, default_chat_id)
            await self._outbound.hydrate(default_chat_id)

            async for raw in connection:
                if isinstance(raw, bytes):
                    try:
                        raw = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        self.logger.warning("ignoring non-utf8 binary frame")
                        continue

                envelope = _parse_envelope(raw)
                if envelope is not None:
                    await self._dispatch_envelope(connection, client_id, envelope)
                    continue

                await self.webui_send_event(connection, "error", detail="Expected a typed WebSocket envelope")
        except Exception as e:
            self.logger.debug("connection ended: {}", e)
        finally:
            await self._cleanup_connection(connection)

    # -- Inbound WebSocket envelopes ---------------------------------------

    async def _dispatch_envelope(
        self,
        connection: ServerConnection,
        client_id: str,
        envelope: dict[str, Any],
    ) -> None:
        """Delegate one typed envelope to the WebUI application router."""
        await self._dispatch_active_envelope(connection, client_id, envelope)

    async def _dispatch_active_envelope(
        self,
        connection: ServerConnection,
        client_id: str,
        envelope: dict[str, Any],
    ) -> None:
        if not self.writers.register(connection):
            return
        await self._commands.dispatch(connection, client_id, envelope)

    # -- Outbound WebSocket events -----------------------------------------

    async def stop(self) -> None:
        server_task = self._server_task
        if (
            not self._running
            and server_task is None
            and not self.writers.connections
            and not self.writers.retire_tasks
        ):
            return
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        for connection in self.writers.connections:
            await self._cleanup_connection(connection)
        if server_task:
            try:
                await server_task
            except asyncio.CancelledError:
                current_task = asyncio.current_task()
                if current_task is not None and current_task.cancelling():
                    raise
                self.logger.debug("server task was already cancelled during shutdown")
            except Exception as e:
                self.logger.warning("server task error during shutdown: {}", e)
            if self._server_task is server_task:
                self._server_task = None
        await self.writers.drain_retirements()
        await self._commands.close()
        await self.gateway.http.workbench.terminals.close_all()
        from cirno_core.observability.recordings import current_recordings
        await asyncio.to_thread(current_recordings().close_all)
        self._subs.clear()
        self._conn_chats.clear()
        self._conn_default.clear()


    @property
    def has_pending_delivery(self) -> bool:
        return self.writers.has_pending

    async def send(self, msg: OutboundMessage) -> None:
        await self._outbound.send(msg)

    def prepare_tool_events(self, msg: OutboundMessage) -> OutboundMessage:
        return msg

    async def send_reasoning_delta(
        self,
        chat_id: str,
        delta: str,
        metadata: dict[str, Any] | None = None,
        *,
        stream_id: str | None = None,
    ) -> None:
        await self._outbound.send_reasoning_delta(chat_id, delta, metadata, stream_id=stream_id)

    async def send_reasoning_end(
        self,
        chat_id: str,
        metadata: dict[str, Any] | None = None,
        *,
        stream_id: str | None = None,
    ) -> None:
        await self._outbound.send_reasoning_end(chat_id, metadata, stream_id=stream_id)

    async def send_file_edit_events(
        self,
        chat_id: str,
        edits: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._outbound.send_file_edit_events(chat_id, edits, metadata)

    async def send_delta(
        self,
        chat_id: str,
        delta: str,
        metadata: dict[str, Any] | None = None,
        *,
        stream_id: str | None = None,
        stream_end: bool = False,
        resuming: bool = False,
        merge_next: bool = False,
    ) -> None:
        await self._outbound.send_delta(
            chat_id, delta, metadata, stream_id=stream_id,
            stream_end=stream_end, resuming=resuming, merge_next=merge_next,
        )
