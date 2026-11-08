"""Model connection settings transport and runtime refresh."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable

from cirno_core.runtime.admission import RuntimeAdmission
from cirno_server.webui.settings.contracts import (
    SettingsRequest,
    SettingsRouteResult,
    WebUISettingsError,
)

if TYPE_CHECKING:
    from cirno_server.webui.settings.services import (
        WebUISettingsServices,
    )


from cirno_server.webui.settings.connection_contracts import ConnectionSettingsOperations


class ConnectionSettingsHandler:
    """Handle model/provider commands after transport authentication and decoding."""

    def __init__(
        self,
        settings: WebUISettingsServices,
        logger: Any,
        admission: RuntimeAdmission,
    ) -> None:
        self.settings = settings
        self.logger = logger
        self._admission = admission
        self._remove_pending_work: Callable[[], None] | None = None
        self._close_task: asyncio.Task[None] | None = None

    async def close(self) -> None:
        """Keep the registry owned even if its shutdown awaiter is cancelled."""
        if self._close_task is None or self._close_task.done():
            self._close_task = asyncio.create_task(
                asyncio.to_thread(self.settings.oauth_flows.close)
            )
            self._close_task.add_done_callback(
                lambda task: task.exception() if not task.cancelled() else None,
            )
        await asyncio.shield(self._close_task)
        if self._remove_pending_work is not None:
            self._remove_pending_work()
            self._remove_pending_work = None

    def _refresh_runtime_config(self) -> None:
        """Make a successful model-settings mutation visible to live clients now."""
        if self.settings.refresh_runtime_config is not None:
            self.settings.refresh_runtime_config()

    async def handle(
        self,
        action: str,
        request: SettingsRequest,
        operations: ConnectionSettingsOperations,
    ) -> SettingsRouteResult:
        if action in {"oauth-login", "oauth-complete", "oauth-logout"}:
            self._admission.check()
            if self._remove_pending_work is None:
                self._remove_pending_work = self._admission.register_pending_work(
                    lambda: self.settings.oauth_flows.has_pending_work,
                )
        try:
            if action == "agent-update":
                payload = await asyncio.to_thread(
                    self.settings.mutate,
                    operations.update_agent,
                    request.query,
                )
                self._refresh_runtime_config()
                return SettingsRouteResult.success(
                    payload,
                    decorate_restart=True,
                    restart_section="runtime",
                )

            if action == "model-update":
                payload = await asyncio.to_thread(
                    self.settings.mutate,
                    operations.update_model,
                    request.query,
                )
                self._refresh_runtime_config()
                return SettingsRouteResult.success(payload, decorate_restart=True)

            mutation = {
                "model-create": operations.create_model,
                "model-delete": operations.delete_model,
                "call-order-update": operations.update_call_order,
                "provider-create": operations.create_provider,
            }.get(action)
            if mutation is not None:
                payload = await asyncio.to_thread(
                    self.settings.mutate,
                    mutation,
                    request.query,
                )
                self._refresh_runtime_config()
                return SettingsRouteResult.success(payload, decorate_restart=True)

            if action == "provider-update":
                payload = await asyncio.to_thread(
                    self.settings.mutate,
                    operations.update_provider,
                    request.query,
                )
                self._refresh_runtime_config()
                return SettingsRouteResult.success(payload, decorate_restart=True)

            if action == "model-api":
                payload = await asyncio.to_thread(
                    self.settings.read,
                    operations.model_api,
                    request.query,
                )
                return SettingsRouteResult.success(payload)

            if action == "provider-balance":
                from cirno_server.webui.settings.balance import provider_balance_payload

                payload = await asyncio.to_thread(
                    self.settings.read, provider_balance_payload, request.query
                )
                return SettingsRouteResult.success(payload)

            if action == "provider-models":
                try:
                    payload = await asyncio.to_thread(
                        self.settings.read,
                        operations.provider_models,
                        request.query,
                    )
                except WebUISettingsError:
                    raise
                except Exception:
                    self.logger.exception("failed to load provider model list")
                    return SettingsRouteResult.failure(
                        500,
                        "failed to load provider model list",
                    )
                return SettingsRouteResult.success(payload)

            if action == "oauth-login":
                payload = await asyncio.to_thread(
                    self.settings.read,
                    operations.oauth_login,
                    request.query,
                    oauth_flows=self.settings.oauth_flows,
                )
            elif action == "oauth-complete":
                raw_response = (request.payload or {}).get("authorization_response")
                if raw_response is not None and not isinstance(raw_response, str):
                    raise WebUISettingsError("OAuth authorization response must be a string")
                payload = await asyncio.to_thread(
                    self.settings.read,
                    operations.oauth_complete,
                    request.query,
                    raw_response or None,
                    oauth_flows=self.settings.oauth_flows,
                )
            elif action == "oauth-logout":
                payload = await asyncio.to_thread(
                    self.settings.read,
                    operations.oauth_logout,
                    request.query,
                    oauth_flows=self.settings.oauth_flows,
                )
            else:
                return SettingsRouteResult.failure(404, "unknown settings action")
        except WebUISettingsError as exc:
            return SettingsRouteResult.failure(exc.status, exc.message)

        if payload.get("status") in {"authorization_required", "pending", "cancelled"}:
            return SettingsRouteResult.success(payload)
        return SettingsRouteResult.success(payload, decorate_restart=True)
