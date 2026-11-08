"""Bootstrap HTTP operations, isolated from transport dispatch."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

from cirno_server.webui.access_tokens import token_response_payload
from cirno_server.webui.http_utils import case_insensitive_header as _case_insensitive_header
from cirno_server.webui.http_utils import host_for_url as _host_for_url
from cirno_server.webui.http_utils import http_error as _http_error
from cirno_server.webui.http_utils import http_json_response as _http_json_response
from cirno_server.webui.http_utils import http_response as _http_response
from cirno_server.webui.http_utils import is_local_browser_request as _is_local_browser_request
from cirno_server.webui.http_utils import (
    is_trusted_proxy_authenticated_request as _is_trusted_proxy_authenticated_request,
)
from cirno_server.webui.http_utils import issue_route_secret_matches as _issue_route_secret_matches
from cirno_server.webui.http_utils import normalize_config_path as _normalize_config_path
from cirno_server.webui.http_utils import safe_host_header as _safe_host_header
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response

from .shared import _NO_STORE_HEADERS, _resolve_bootstrap_model_name

if TYPE_CHECKING:
    from .handler import ServerHTTPHandler


class BootstrapRoutes:
    def __init__(self, server: ServerHTTPHandler) -> None:
        self.server = server

    def _handle_token_issue(self, connection: Any, request: Any) -> Any:
        secret = self.server.config.token_issue_secret.strip() or self.server.config.token.strip()
        if secret:
            if not _issue_route_secret_matches(request.headers, secret):
                return connection.respond(401, "Unauthorized")
        else:
            self.server._log.warning(
                "token_issue_path is set but token_issue_secret is empty; "
                "any client can obtain connection tokens — set token_issue_secret for production."
            )
        if not self.server.tokens.can_issue():
            self.server._log.error(
                "too many outstanding issued tokens ({}), rejecting issuance",
                len(self.server.tokens.issued_tokens),
            )
            return _http_json_response(
                {"error": "too many outstanding tokens"},
                status=429,
                extra_headers=_NO_STORE_HEADERS,
            )
        token_value = self.server.tokens.issue_token(self.server.config.token_ttl_s)
        return _http_json_response(
            token_response_payload(token_value, self.server.config.token_ttl_s),
            extra_headers=_NO_STORE_HEADERS,
        )

    def _handle_bootstrap(
        self,
        connection: Any,
        request: Any,
        *,
        terminal_probe: bool = False,
    ) -> Response:
        secret = self.server.config.token_issue_secret.strip() or self.server.config.token.strip()
        owner = self.server.auth.store.owner() if self.server.auth.enabled else None
        if self.server.auth.enabled:
            if owner is None:
                return _http_json_response(
                    {"error": "registration_required"}, status=428, extra_headers=_NO_STORE_HEADERS
                )
            if not self.server.auth.authenticated(request.headers):
                return _http_json_response(
                    {"error": "login_required"}, status=401, extra_headers=_NO_STORE_HEADERS
                )
        is_local_browser = _is_local_browser_request(connection, request.headers)
        is_proxy_authenticated = _is_trusted_proxy_authenticated_request(
            connection,
            request.headers,
            self.server.config,
        )
        if not self.server.auth.enabled and not is_proxy_authenticated:
            if secret:
                if not _issue_route_secret_matches(request.headers, secret):
                    return _http_error(401, "Unauthorized")
            elif not is_local_browser:
                return _http_error(403, "bootstrap is localhost-only")

        from cirno_server.webui.client_contract import gateway_identity

        terminal = gateway_identity(self.server.tokens.instance_id)
        if terminal_probe:
            # Capability probing does not allocate credentials or acquire client leases.
            return _http_json_response(terminal, extra_headers=_NO_STORE_HEADERS)

        if is_proxy_authenticated and not self.server.auth.enabled:
            payload = {
                "ws_path": _normalize_config_path(self.server.config.path),
                "ws_url": self.server.bootstrap_routes._bootstrap_ws_url(request),
                "limits": self.server.ingress.bootstrap_limits(
                    max_frame_bytes=self.server.config.max_message_bytes,
                ),
                "model_name": _resolve_bootstrap_model_name(
                    self.server.runtime_model_name,
                    self.server.settings.config.path,
                ),
                "terminal": terminal,
            }
            payload["preferences"] = self.server.preferences.read()
            return _http_json_response(payload, extra_headers=_NO_STORE_HEADERS)

        api_token_allowed = self.server.auth.enabled or bool(secret) or is_local_browser
        if not self.server.tokens.can_issue(include_api_token=api_token_allowed):
            return _http_response(
                json.dumps({"error": "too many outstanding tokens"}).encode("utf-8"),
                status=429,
                content_type="application/json; charset=utf-8",
                extra_headers=_NO_STORE_HEADERS,
            )
        browser_session = (
            self.server.auth.cookie(request.headers) if self.server.auth.enabled else ""
        )
        token = self.server.tokens.issue_token(
            self.server.config.token_ttl_s, audience="webui", browser_session=browser_session
        )
        api_token = (
            self.server.tokens.issue_api_token(
                self.server.config.token_ttl_s, browser_session=browser_session
            )
            if api_token_allowed
            else None
        )

        ws_url = self.server.bootstrap_routes._bootstrap_ws_url(request)
        expected_path = _normalize_config_path(self.server.config.path)
        payload = {
            "token": token,
            "browser_auth": self.server.auth.enabled,
            "onboarding_required": bool(owner and not owner[1]),
            "terminal": terminal,
            "ws_path": expected_path,
            "ws_url": ws_url,
            "expires_in": self.server.config.token_ttl_s,
            "limits": self.server.ingress.bootstrap_limits(
                max_frame_bytes=self.server.config.max_message_bytes,
            ),
            "model_name": _resolve_bootstrap_model_name(
                self.server.runtime_model_name,
                self.server.settings.config.path,
            ),
        }
        if api_token is not None:
            payload["api_token"] = api_token
        payload["preferences"] = self.server.preferences.read()
        return _http_json_response(payload, extra_headers=_NO_STORE_HEADERS)

    def _bootstrap_ws_url(self, request: Any) -> str:
        headers = getattr(request, "headers", {}) or {}
        if self.server.config.public_ws_url:
            return self.server.config.public_ws_url
        host = _safe_host_header(_case_insensitive_header(headers, "Host"))
        if not host:
            host = _host_for_url(self.server.config.host, self.server.config.port)
        proto = _case_insensitive_header(headers, "X-Forwarded-Proto")
        proto = proto.split(",", 1)[0].strip().lower()
        secure = proto in {"https", "wss"} or bool(self.server.config.ssl_certfile.strip())
        scheme = "wss" if secure else "ws"
        expected_path = _normalize_config_path(self.server.config.path)
        return f"{scheme}://{host}{expected_path}"

    def _mcp_oauth_redirect_uri(self, request: WsRequest) -> str:
        """Derive the browser callback from the same public origin as WebSocket bootstrap."""
        from cirno_core.agent.tools.mcp_oauth import MCP_OAUTH_CALLBACK_PATH

        public_ws_url = urlsplit(self.server.bootstrap_routes._bootstrap_ws_url(request))
        scheme = "https" if public_ws_url.scheme == "wss" else "http"
        return urlunsplit((scheme, public_ws_url.netloc, MCP_OAUTH_CALLBACK_PATH, "", ""))
