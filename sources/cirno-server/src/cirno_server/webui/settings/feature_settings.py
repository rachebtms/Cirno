"""Feature installation receipts, pending restarts and live channel application."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from cirno_server.features.service import OptionalFeatureError, with_channel_runtime_status
from cirno_server.webui.settings.contracts import (
    QueryParams, SettingsRequest, SettingsRouteResult, query_first,
)
from cirno_server.webui.settings.system_contracts import SystemSettingsOperations

if TYPE_CHECKING:
    from cirno_server.webui.settings.services import WebUISettingsServices


def _runtime_receipt(
    payload: dict[str, Any], *, message: str, requires_restart: bool, ok: bool | None = None,
) -> dict[str, Any]:
    last_action = dict(payload.get("last_action") or {})
    previous = last_action.get("message")
    last_action["message"] = f"{previous}. {message}" if isinstance(previous, str) and previous else message
    last_action["hot_reload"] = not requires_restart
    if ok is not None:
        last_action["ok"] = ok
    return {**payload, "requires_restart": requires_restart, "last_action": last_action}


class FeatureSettings:
    def __init__(self, settings: WebUISettingsServices, logger: Any) -> None:
        self.settings = settings
        self.logger = logger
        self.pending_restarts: set[str] = set()

    async def list(
        self,
        operations: SystemSettingsOperations,
    ) -> SettingsRouteResult:
        try:
            payload = await asyncio.to_thread(
                operations.cirno_features_payload,
                config_path=self.settings.config.path,
            )
        except Exception:
            self.logger.exception("failed to load cirno features")
            return SettingsRouteResult.failure(500, "failed to load cirno features")
        return SettingsRouteResult.success(
            self.with_runtime_status(payload, operations)
        )

    def read(
        self,
        operations: SystemSettingsOperations,
    ) -> dict[str, Any]:
        return operations.cirno_features_payload(config_path=self.settings.config.path)

    def mutate(
        self,
        action: str,
        query: QueryParams,
        operations: SystemSettingsOperations,
    ) -> dict[str, Any]:
        name = (query_first(query, "name") or "").strip()
        raw_install_only = query_first(query, "install_only")
        install_only = (raw_install_only or "").strip().lower() in {
            "1", "true", "yes",
        }
        # Malformed values still pass through the feature API's validation.
        ordinary_enable = raw_install_only is None or raw_install_only.strip().lower() in {
            "0", "false", "no",
        }

        def change(*, config_path: Path) -> dict[str, Any]:
            # Keep the dependency marker and config mutation under the same
            # lock: another enable must not import the new code in between.
            if action == "enable" and ordinary_enable and name in self.pending_restarts:
                return self.runtime_fallback(
                    operations.cirno_features_payload(config_path=config_path),
                    message=f"Restart Cirno before enabling newly installed support for {name}.",
                )
            payload = operations.cirno_features_action(action, query, config_path=config_path)
            if action == "enable" and (
                (install_only and payload.get("requires_restart"))
                or payload.get("last_action", {}).get("dependencies_installed")
            ):
                self.pending_restarts.add(name)
            return payload

        return self.settings.mutate(change)

    async def action(
        self,
        request: SettingsRequest,
        action: str,
        operations: SystemSettingsOperations,
    ) -> SettingsRouteResult:
        install_only = (
            action == "enable"
            and (query_first(request.query, "install_only") or "").strip().lower()
            in {"1", "true", "yes"}
        )
        try:
            payload = await asyncio.to_thread(
                self.mutate,
                action,
                request.query,
                operations,
            )
        except OptionalFeatureError as exc:
            return SettingsRouteResult.failure(exc.status, exc.message)
        except Exception as exc:
            status = getattr(exc, "status", 500)
            message = getattr(exc, "message", str(exc))
            if status >= 500:
                self.logger.exception(
                    "cirno feature action '{}' failed",
                    action,
                )
            return SettingsRouteResult.failure(status, message)
        if not install_only:
            payload = await self.apply_runtime_change(
                action,
                request.query,
                payload,
                operations,
            )
        payload = self.with_runtime_status(payload, operations)
        return SettingsRouteResult.success(
            payload,
            decorate_restart=True,
            restart_section="runtime",
        )

    def with_runtime_status(
        self,
        payload: dict[str, Any],
        operations: SystemSettingsOperations,
    ) -> dict[str, Any]:
        if operations.channel_runtime_status is not None:
            try:
                payload = with_channel_runtime_status(
                    payload,
                    operations.channel_runtime_status(),
                )
            except Exception:
                self.logger.exception("failed to load channel runtime status")
        return {
            **payload,
            "features": [
                {**feature, "restart_pending": feature["name"] in self.pending_restarts}
                if feature["type"] == "channel" else feature
                for feature in payload["features"]
            ],
        }

    async def apply_runtime_change(
        self,
        action: str,
        query: QueryParams,
        payload: dict[str, Any],
        operations: SystemSettingsOperations,
    ) -> dict[str, Any]:
        if operations.channel_feature_action is None:
            return payload
        name = (query_first(query, "name") or "").strip()
        if not name:
            return payload
        if action == "enable" and name in self.pending_restarts:
            if payload.get("last_action", {}).get("hot_reload") is False:
                return payload
            return self.runtime_fallback(
                payload,
                message=f"New support for {name} was installed. Restart Cirno before applying this channel.",
            )
        try:
            instance_id = operations.cirno_feature_instance_target(query)
            result = operations.channel_feature_action(action, name, instance_id)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            self.logger.exception("failed to apply channel '{}' without restart", name)
            return self.runtime_fallback(
                payload,
                message=(
                    f"{name} channel config was saved, but hot reload failed: {exc}"
                ),
            )

        if not isinstance(result, dict):
            return payload
        result = cast(dict[str, Any], result)
        if not result.get("handled"):
            return payload

        requires_restart = bool(result.get("requires_restart"))
        message = result.get("message")
        if isinstance(message, str) and message:
            return _runtime_receipt(
                payload, message=message, requires_restart=requires_restart,
                ok=bool(result["ok"]) if "ok" in result else None,
            )
        return {**payload, "requires_restart": requires_restart}

    @staticmethod
    def runtime_fallback(
        payload: dict[str, Any],
        *,
        message: str,
    ) -> dict[str, Any]:
        return _runtime_receipt(payload, message=message, requires_restart=True)
