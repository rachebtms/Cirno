"""HTTP transport admission and explicit controller composition."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from cirno_core.runtime.admission import RuntimeMaintenanceError
from cirno_core.session.manager import SessionManager
from cirno_server.webui.access_tokens import ServerTokenStore
from cirno_server.webui.http_utils import combined_list_header as _combined_list_header
from cirno_server.webui.http_utils import http_error as _http_error
from cirno_server.webui.http_utils import http_json_response as _http_json_response
from cirno_server.webui.http_utils import (
    is_trusted_proxy_authenticated_request as _is_trusted_proxy_authenticated_request,
)
from cirno_server.webui.http_utils import normalize_config_path as _normalize_config_path
from cirno_server.webui.http_utils import parse_query as _parse_query
from cirno_server.webui.http_utils import parse_request_path as _parse_request_path
from cirno_server.webui.ingress_policy import WebUIIngressPolicy
from cirno_server.webui.media_gateway import WebUIMediaServer
from cirno_server.webui.workspaces import WebUIWorkspaceController
from loguru import logger
from websockets.datastructures import Headers
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response

from .assets import AssetsRoutes
from .automations import AutomationsRoutes
from .bootstrap import BootstrapRoutes
from .files import FilesRoutes
from .history import HistoryRoutes
from .navigation import NavigationRoutes
from .recovery import RecoveryRoutes
from .sessions import SessionsRoutes
from .shared import (
    _NO_STORE_HEADERS,
    _SLOW_WEBUI_HTTP_LOG_MS,
    _WEBUI_CHANNEL_CONNECT_ACTIONS,
    _WEBUI_MUTATION_PATHS,
    _WEBUI_MUTATION_PAYLOAD_ATTR,
    _WEBUI_MUTATION_REQUEST_ATTR,
    _mutation_payload,
)
from .sidebar import SidebarRoutes
from .skills import SkillsRoutes


class ServerHTTPHandler:
    def __init__(
        self,
        *,
        config: WebSocketConfig,
        session_manager: SessionManager | None,
        static_dist_path: Path | None,
        runtime_model_name: Callable[[], str | None] | None,
        bus: MessageBus,
        tokens: ServerTokenStore,
        media: WebUIMediaServer,
        ingress: WebUIIngressPolicy,
        workspaces: WebUIWorkspaceController,
        settings: WebUISettingsServices,
        skills_workspace_path: Path,
        disabled_skills: set[str] | None = None,
        cron_service: CronService | None = None,
        local_trigger_store: LocalTriggerStore | None = None,
        cron_pending_job_ids: Callable[[str], set[str]] | None = None,
        local_trigger_pending_ids: Callable[[str], set[str]] | None = None,
        channel_feature_action: Callable[..., Any] | None = None,
        channel_runtime_status: Callable[[], dict[str, Any]] | None = None,
        mcp_runtime_status: Callable[[], Mapping[str, str]] | None = None,
        mcp_reload: Callable[[], Awaitable[dict[str, Any]]] | None = None,
        skill_state_action: Callable[[set[str]], None] | None = None,
        recovery_action: (Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None) = None,
        subagent_manager: SubagentManager | None = None,
        discard_session: Callable[[str], Awaitable[None]] | None = None,
        context_usage: Callable[[str], Awaitable[dict[str, Any]]] | None = None,
        log: Any = logger,
    ) -> None:
        self.config = config
        self.session_manager = session_manager
        self.static_dist_path = static_dist_path.resolve() if static_dist_path is not None else None
        self.runtime_model_name = runtime_model_name
        self.bus = bus
        self.tokens = tokens
        self.media = media
        self.ingress = ingress
        self.workspaces = workspaces
        from cirno_server.webui.workbench_api import WorkbenchAPI

        self.workbench = WorkbenchAPI(workspaces, session_manager)
        self.settings = settings
        from cirno_core.profile.preferences import PreferencesRepository

        self.preferences = PreferencesRepository(
            settings.config.path.parent / "state" / "preferences.sqlite3"
        )
        from cirno_server.webui.auth.routes import BrowserAuth
        from cirno_server.webui.auth.store import AccountStore

        from cirno_server.webui.auth.router_identity import RouterIdentity
        self.auth = BrowserAuth(
            AccountStore(settings.config.path.parent / "state" / "webui-auth.sqlite3"),
            enabled=config.browser_setup,
            router=RouterIdentity(session_manager, bus) if session_manager is not None else None,
        )
        self.skills_workspace_path = skills_workspace_path
        self.disabled_skills: set[str] = disabled_skills if disabled_skills is not None else set()
        self.skill_state_action = skill_state_action
        self.recovery_action = recovery_action
        self.subagent_manager = subagent_manager
        self.discard_session = discard_session
        self.context_usage = context_usage
        self._skill_install_lock = asyncio.Lock()
        self.cron_service = cron_service
        self.local_trigger_store = local_trigger_store
        self.cron_pending_job_ids = cron_pending_job_ids
        self.channel_runtime_status = channel_runtime_status
        self.local_trigger_pending_ids = local_trigger_pending_ids
        self._log = log

        from cirno_server.webui.settings.routes import WebUISettingsRouter

        self.assets_routes = AssetsRoutes(self)
        self.automations_routes = AutomationsRoutes(self)
        self.bootstrap_routes = BootstrapRoutes(self)
        self.files_routes = FilesRoutes(self)
        self.history_routes = HistoryRoutes(self)
        self.navigation_routes = NavigationRoutes(self)
        self.recovery_routes = RecoveryRoutes(self)
        self.sessions_routes = SessionsRoutes(self)
        self.sidebar_routes = SidebarRoutes(self)
        self.skills_routes = SkillsRoutes(self)

        self.settings_routes = WebUISettingsRouter(
            settings=settings,
            bus=bus,
            logger=self._log,
            check_api_token=self.check_api_token,
            parse_query=_parse_query,
            json_response=_http_json_response,
            error_response=_http_error,
            channel_feature_action=channel_feature_action,
            channel_runtime_status=channel_runtime_status,
            mcp_runtime_status=mcp_runtime_status,
            mcp_reload=mcp_reload,
            mcp_oauth_redirect_uri=self.bootstrap_routes._mcp_oauth_redirect_uri,
        )

    def workspace_project_selection_available(self, connection: Any) -> bool:
        """Return whether an authenticated WebUI may submit a server path.

        Project paths are interpreted by the gateway, not by the browser. The
        WebUI route and WebSocket handshake already authenticate the caller,
        so remote clients can use the manual server-path picker as well.
        """
        return True

    def check_api_token(self, request: WsRequest) -> bool:
        if getattr(request, "_cirno_trusted_proxy_authenticated", False):
            return True
        return self.tokens.check_api_token(request)

    async def dispatch(self, connection: Any, request: WsRequest) -> Any | None:
        """Route an HTTP request. Returns Response or None."""
        got, _ = _parse_request_path(request.path)
        started = time.perf_counter()
        response: Any | None = None
        setattr(
            request,
            "_cirno_trusted_proxy_authenticated",
            not self.auth.enabled
            and _is_trusted_proxy_authenticated_request(connection, request.headers, self.config),
        )

        try:
            if self._is_webui_mutation_path(got):
                return _http_error(
                    405,
                    "WebUI mutations require an authenticated WebSocket",
                )
            with self.bus.admission.activity():
                response = await self._dispatch_resolved(connection, request, got)
            return response
        except RuntimeMaintenanceError:
            return _http_error(503, "Server update is being verified. Retry shortly.")
        finally:
            self._log_slow_http(got, response, started)

    async def dispatch_webui_mutation(
        self,
        connection: Any,
        action: str,
        payload: dict[str, Any],
    ) -> Response:
        """Run one explicitly allowlisted mutation for an authenticated WebUI socket."""
        if action == "connection.check":
            return _http_json_response({"connected": True})
        path = self._webui_mutation_path(action, payload)
        if isinstance(path, Response):
            return path

        source_request = getattr(connection, "request", None)
        source_headers = getattr(source_request, "headers", None)
        if source_headers is None:
            headers = Headers()
        else:
            try:
                headers = Headers(source_headers.raw_items())
            except (AttributeError, TypeError):
                try:
                    headers = Headers(source_headers)
                except TypeError:
                    headers = Headers()
        request = WsRequest(path, headers)
        setattr(request, "_cirno_trusted_proxy_authenticated", True)
        setattr(request, _WEBUI_MUTATION_REQUEST_ATTR, True)
        setattr(request, _WEBUI_MUTATION_PAYLOAD_ATTR, dict(payload))
        try:
            # WebUI mutation tasks already survive a disconnected browser. Keep
            # their async/threaded writes busy until that operation really ends.
            with self.bus.admission.activity():
                response = await self._dispatch_resolved(connection, request, path)
        except RuntimeMaintenanceError:
            return _http_error(503, "Server update is being verified. Retry shortly.")
        if isinstance(response, Response):
            return response
        return _http_error(404, "WebUI mutation action not found")

    def _is_webui_mutation_path(self, path: str) -> bool:
        if path == "/v0/instance":
            return True
        if path == "/v0/session-context":
            return True
        if path.startswith("/v0/workspaces/files/"):
            return True
        if self.settings_routes.is_mutation_path(path):
            return True
        if re.match(r"^/v0/sessions/[^/]+/delete$", path):
            return True
        if re.match(
            r"^/v0/webui/automations/(enable|disable|delete|run|update|change-chat)$", path
        ):
            return True
        if path in {"/v0/webui/recovery/continue", "/v0/webui/recovery/dismiss"}:
            return True
        return path in {
            "/v0/webui/skills/install",
            "/v0/webui/skills/update",
            "/v0/webui/skills/delete",
            "/v0/webui/star-prompt/claim",
            "/v0/webui/star-prompt/dismiss",
            "/v0/webui/sidebar-state/update",
            "/v0/workspaces/resolve-project",
            "/v0/workspaces/favorite",
            "/v0/webui/subagents/cancel",
        }

    @staticmethod
    def _webui_mutation_path(
        action: str,
        payload: dict[str, Any],
    ) -> str | Response:
        path = _WEBUI_MUTATION_PATHS.get(action)
        if path is not None:
            return path
        if action == "session.delete":
            key = payload.get("key")
            if not isinstance(key, str) or not key.strip():
                return _http_error(400, "missing session key")
            return f"/v0/sessions/{quote(key, safe='')}/delete"
        connect_action = _WEBUI_CHANNEL_CONNECT_ACTIONS.get(action)
        if connect_action is not None:
            channel = payload.get("channel")
            if (
                not isinstance(channel, str)
                or re.fullmatch(
                    r"[A-Za-z0-9_-]{1,64}",
                    channel,
                )
                is None
            ):
                return _http_error(400, "invalid channel name")
            return f"/v0/settings/channels/{channel}/connect/{connect_action}"
        return _http_error(404, "unknown WebUI mutation action")

    async def _dispatch_resolved(
        self,
        connection: Any,
        request: WsRequest,
        got: str,
    ) -> Any | None:
        if got == "/v0/auth/status":
            status = await self.auth.account_status(request.headers)
            return _http_json_response(status, extra_headers=_NO_STORE_HEADERS)
        if got.startswith("/v0/auth/"):
            return _http_error(405, "Authentication changes require POST")
        # Token issue endpoint
        if self.config.token_issue_path:
            issue_expected = _normalize_config_path(self.config.token_issue_path)
            if got == issue_expected:
                if self.auth.enabled:
                    return _http_error(403, "Use browser login to obtain WebUI tokens")
                return self.bootstrap_routes._handle_token_issue(connection, request)

        # Bootstrap
        if got == "/v0/bootstrap":
            return self.bootstrap_routes._handle_bootstrap(connection, request)
        if got == "/v0/connection":
            return self.bootstrap_routes._handle_bootstrap(connection, request, terminal_probe=True)

        if got == "/v0/preferences":
            from .preferences import preferences_response

            return await preferences_response(self, request)

        if got == "/v0/workbench":
            if not getattr(request, _WEBUI_MUTATION_REQUEST_ATTR, False):
                return _http_error(405, "Workbench actions require an authenticated WebSocket")
            try:
                result = await self.workbench.action(_mutation_payload(request) or {})
            except (ValueError, KeyError, RuntimeError, OSError) as exc:
                return _http_error(400, str(exc))
            return _http_json_response(result, extra_headers=_NO_STORE_HEADERS)

        if got == "/v0/instance":
            if not self.check_api_token(request):
                return _http_error(401, "Unauthorized")
            from cirno_server.webui.instance_api import instance_action

            try:
                result = await instance_action(
                    _mutation_payload(request) or {}, sessions=self.session_manager, bus=self.bus
                )
            except (ValueError, KeyError, RuntimeError, OSError) as exc:
                return _http_error(400, str(exc))
            return _http_json_response(result, extra_headers=_NO_STORE_HEADERS)

        if got == "/v0/session-context":
            return await self.navigation_routes._handle_session_context(request)

        # Settings routes (delegated)
        response = await self.settings_routes.dispatch(connection, request, got)
        if response is not None:
            return response

        # Recovery routes
        response = await self.recovery_routes._dispatch_recovery_route(request, got)
        if response is not None:
            return response

        if got == "/v0/webui/subagents/cancel":
            return await self.recovery_routes._handle_subagent_cancel(request)

        # Session routes
        response = await self.sessions_routes._dispatch_session_routes(request, got)
        if response is not None:
            return response

        # Automation routes
        response = await self.automations_routes._dispatch_automation_routes(request, got)
        if response is not None:
            return response

        # Misc routes
        response = await self.navigation_routes._dispatch_misc_routes(connection, request, got)
        if response is not None:
            return response

        # Unsupported API versions must never fall through to the SPA.
        if re.match(r"^/v\d+(?:/|$)", got):
            return _http_error(404, "API route not found")

        # Static SPA serving
        if self.static_dist_path is not None:
            response = self.assets_routes._serve_static(
                got,
                accept_encoding=_combined_list_header(request.headers, "Accept-Encoding"),
            )
            if response is not None:
                return response

        return connection.respond(404, "Not Found")

    def _log_slow_http(self, path: str, response: Any | None, started: float) -> None:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if elapsed_ms < _SLOW_WEBUI_HTTP_LOG_MS:
            return
        if not (path.startswith("/v0/") or path == "/v0/bootstrap"):
            return
        if path.endswith("/webui-thread"):
            return
        status = getattr(response, "status_code", None)
        self._log.warning(
            "slow webui http route path={} status={} duration_ms={}",
            path,
            status if status is not None else "none",
            elapsed_ms,
        )


if TYPE_CHECKING:
    from cirno_core.agent.subagents.manager import SubagentManager
    from cirno_core.bus.queue import MessageBus
    from cirno_core.cron.service import CronService
    from cirno_core.triggers.local_store import LocalTriggerStore
    from cirno_server.channels.websocket.config import WebSocketConfig
    from cirno_server.webui.settings.services import WebUISettingsServices
