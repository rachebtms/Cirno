"""Providers mutations."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from cirno_core.config.models import ModelPresetConfig
from cirno_core.config.schema import Config
from cirno_core.providers.registry import PROVIDERS, find_by_name
from cirno_core.providers.routing import resolve_model_api
from cirno_server.webui.settings import requests as request_settings
from cirno_server.webui.settings.contracts import (
    QueryParams,
    WebUISettingsError,
    parse_bool,
    query_first,
    query_first_alias,
    query_has_alias,
)
from cirno_server.webui.settings.providers.oauth import _OAUTH_PROXY_PROVIDERS
from cirno_server.webui.settings.providers.state import (
    _dynamic_provider_items,
    _provider_advanced_field_names,
    resolve_settings_provider,
)


def _provider_config_updates(query: QueryParams) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    string_fields = (
        ("api_key", "apiKey"),
        ("api_base", "apiBase"),
        ("thinking_style", "thinkingStyle"),
        ("region", "region"),
        ("profile", "profile"),
        ("display_name", "displayName"),
    )
    for snake, camel in string_fields:
        if query_has_alias(query, snake, camel):
            value = (query_first_alias(query, snake, camel) or "").strip()
            updates[snake] = value or None

    if query_has_alias(query, "use_proxy", "useProxy"):
        updates["use_proxy"] = parse_bool(
            query_first_alias(query, "use_proxy", "useProxy") or "", "use_proxy"
        )

    for snake, camel in (
        ("extra_headers", "extraHeaders"),
        ("extra_body", "extraBody"),
        ("extra_query", "extraQuery"),
    ):
        if query_has_alias(query, snake, camel):
            updates[snake] = request_settings.parse_request_object(query, snake, camel)
    if query_has_alias(query, "api", "api"):
        try:
            updates["api"] = json.loads(query_first(query, "api") or "null")
        except ValueError as exc:
            raise WebUISettingsError(
                "api must declare supportedApis and a preferredApi from that list"
            ) from exc
    if "balance" in query:
        try:
            updates["balance"] = json.loads(query_first(query, "balance") or "null")
        except ValueError as error:
            raise WebUISettingsError("Balance settings must be a JSON object or null") from error
    return updates


def _provider_display_name_exists(
    config: Config,
    display_name: str,
    *,
    exclude_key: str | None = None,
) -> bool:
    normalized = display_name.strip().casefold()
    if any(spec.label.strip().casefold() == normalized for spec in PROVIDERS):
        return True
    for provider_key, provider_config in _dynamic_provider_items(config):
        if provider_key == exclude_key:
            continue
        label = (
            provider_config.display_name or provider_key.replace("-", " ").replace("_", " ").title()
        )
        if label.strip().casefold() == normalized:
            return True
    return False


def create_provider_settings(config: Config, query: QueryParams) -> str:
    display_name = (query_first_alias(query, "name", "displayName") or "").strip()
    if not display_name:
        raise WebUISettingsError("provider name is required")
    if len(display_name) > 80:
        raise WebUISettingsError("provider name must be 80 characters or fewer")
    updates = _provider_config_updates(query)
    if updates.get("use_proxy"):
        try:
            config.network.resolve_proxy(True)
        except ValueError as exc:
            raise WebUISettingsError(str(exc)) from None
    allowed = {
        "api_key",
        "api_base",
        "use_proxy",
        "extra_headers",
        "extra_body",
        "extra_query",
        "thinking_style",
        "display_name",
        "api",
        "balance",
    }
    unsupported = set(updates) - allowed
    if unsupported:
        field = sorted(unsupported)[0]
        raise WebUISettingsError(f"{field} is not supported for a custom provider")
    api_base = str(updates.get("api_base") or "")
    if not api_base:
        raise WebUISettingsError("API base is required")
    if _provider_display_name_exists(config, display_name):
        raise WebUISettingsError("provider already exists", status=409)

    provider_key = f"provider-{uuid4().hex}"
    updates["display_name"] = display_name
    provider_config = request_settings.validate_request_config(None, updates)
    setattr(config.providers, provider_key, provider_config)
    return provider_key


def update_provider_settings(
    config: Config,
    query: QueryParams,
) -> tuple[bool, bool]:
    provider_name = (query_first(query, "provider") or "").strip()
    if not provider_name:
        raise WebUISettingsError("provider is required")

    resolved_provider = resolve_settings_provider(config, provider_name)
    if resolved_provider is None:
        raise WebUISettingsError("unknown provider")
    spec, provider_key, provider_config = resolved_provider
    updates = _provider_config_updates(query)
    if updates.get("use_proxy"):
        try:
            config.network.resolve_proxy(True)
        except ValueError as exc:
            raise WebUISettingsError(str(exc)) from None
    if spec.is_oauth:
        if spec.name not in _OAUTH_PROXY_PROVIDERS:
            raise WebUISettingsError("unknown provider")
        unsupported = set(updates) - {"use_proxy", "extra_body", "balance"}
        if unsupported:
            raise WebUISettingsError(
                "OAuth provider only supports use_proxy and extra_body settings"
            )
    else:
        allowed = {
            "api_key",
            "api_base",
            "balance",
            *_provider_advanced_field_names(provider_key, spec),
        }
        if find_by_name(provider_key) is None:
            allowed.add("display_name")
        if spec.provider_api_configurable:
            allowed.add("api")
        unsupported = set(updates) - allowed
        if unsupported:
            field = sorted(unsupported)[0]
            raise WebUISettingsError(f"{field} is not supported for this provider")

    if "display_name" in updates:
        display_name = str(updates["display_name"] or "")
        if not display_name:
            raise WebUISettingsError("provider name is required")
        if len(display_name) > 80:
            raise WebUISettingsError("provider name must be 80 characters or fewer")
        if _provider_display_name_exists(config, display_name, exclude_key=provider_key):
            raise WebUISettingsError("provider already exists", status=409)

    updated_provider_config = request_settings.validate_request_config(provider_config, updates)
    if updated_provider_config.api != provider_config.api:
        candidates = [
            *config.model_presets.values(),
            config.agents.defaults,
            *(
                fallback
                for fallback in config.agents.defaults.fallback_models
                if not isinstance(fallback, str)
            ),
        ]
        try:
            resolve_model_api(spec, updated_provider_config, None)
            for candidate in candidates:
                preset = ModelPresetConfig(
                    model=candidate.model, provider=candidate.provider, api=candidate.api
                )
                if config.get_provider_name(preset.model, preset=preset) == provider_key:
                    resolve_model_api(spec, updated_provider_config, preset.api)
        except ValueError as exc:
            raise WebUISettingsError(str(exc)) from None
    changed = updated_provider_config != provider_config
    if changed:
        setattr(config.providers, provider_key, updated_provider_config)
    return changed, False
