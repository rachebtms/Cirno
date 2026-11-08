from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from cirno_server.channels.websocket.config import WebSocketConfig
from cirno_server.webui.http import ServerHTTPHandler
from cirno_server.webui.http.bootstrap import BootstrapRoutes
from websockets.datastructures import Headers
from websockets.http11 import Request as WsRequest


def _handler(config: WebSocketConfig) -> ServerHTTPHandler:
    handler = object.__new__(ServerHTTPHandler)
    handler.config = config
    handler.bootstrap_routes = BootstrapRoutes(handler)
    return handler


def _request(**headers: str) -> WsRequest:
    return cast(WsRequest, SimpleNamespace(headers=Headers(headers)))


def test_mcp_oauth_callback_uses_configured_public_websocket_origin() -> None:
    handler = _handler(WebSocketConfig(path="/v0/ws", public_ws_url="wss://agent.example/v0/ws"))

    redirect_uri = handler.bootstrap_routes._mcp_oauth_redirect_uri(_request(Host="ignored.example"))

    assert redirect_uri == "https://agent.example/v0/mcp/oauth/callback"


def test_mcp_oauth_callback_uses_safe_forwarded_request_origin() -> None:
    handler = _handler(WebSocketConfig(path="/v0/ws", host="127.0.0.1", port=8765))

    redirect_uri = handler.bootstrap_routes._mcp_oauth_redirect_uri(
        _request(Host="cirno.example:9443", **{"X-Forwarded-Proto": "https"})
    )

    assert redirect_uri == "https://cirno.example:9443/v0/mcp/oauth/callback"
