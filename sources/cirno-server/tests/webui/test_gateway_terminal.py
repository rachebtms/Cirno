"""Terminal capability metadata is authenticated and does not allocate tokens."""

import json
from types import SimpleNamespace

from cirno_server.channels.websocket.config import WebSocketConfig
from cirno_server.webui.access_tokens import ServerTokenStore
from cirno_server.webui.auth.routes import BrowserAuth
from cirno_server.webui.auth.store import AccountStore
from cirno_server.webui.client_contract import gateway_identity
from cirno_server.webui.http import ServerHTTPHandler
from cirno_server.webui.http.bootstrap import BootstrapRoutes
from websockets.datastructures import Headers
from websockets.http11 import Request


def test_terminal_probe_is_private_stable_and_does_not_issue_credentials(tmp_path):
    handler = object.__new__(ServerHTTPHandler)
    handler.bootstrap_routes = BootstrapRoutes(handler)
    handler.config = WebSocketConfig(token_issue_secret="fixture-secret")
    handler.auth = BrowserAuth(AccountStore(tmp_path / "webui-auth.sqlite3"), enabled=False)
    handler.tokens = ServerTokenStore(max_tokens=0)
    connection = SimpleNamespace(remote_address=("127.0.0.1", 10000))
    request = Request("/v0/connection", Headers({"Host": "127.0.0.1:8765"}))
    assert handler.bootstrap_routes._handle_bootstrap(connection, request, terminal_probe=True).status_code == 401
    request.headers["X-Cirno-Auth"] = "fixture-secret"
    for _ in range(3):
        response = handler.bootstrap_routes._handle_bootstrap(connection, request, terminal_probe=True)
        assert response.status_code == 200
        assert json.loads(response.body) == gateway_identity(handler.tokens.instance_id)
        assert "no-store" in response.headers["Cache-Control"]
    assert not handler.tokens.api_tokens and not handler.tokens.issued_tokens
    assert ServerTokenStore().instance_id != handler.tokens.instance_id
