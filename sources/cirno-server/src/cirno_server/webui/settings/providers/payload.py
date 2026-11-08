"""Providers payload."""

from __future__ import annotations

from typing import Any

from cirno_core.config.providers import ProviderConfig
from cirno_core.config.schema import Config
from cirno_core.providers.catalog.contracts import ProviderSpec
from cirno_core.providers.registry import PROVIDERS, find_by_name
from cirno_server.webui.settings import requests as request_settings
from cirno_server.webui.settings.connection_contracts import OAuthStatusReader
from cirno_server.webui.settings.models.catalog import model_catalog_kind
from cirno_server.webui.settings.providers.state import (
    _provider_advanced_field_names,
    mask_secret_hint,
    provider_configured_for_settings,
    provider_requires_api_key,
)


def _provider_settings_row(
    name: str,
    spec: ProviderSpec,
    provider_config: ProviderConfig,
    oauth_status_reader: OAuthStatusReader,
) -> dict[str, Any]:
    oauth_status = oauth_status_reader(spec) if spec.is_oauth else None
    is_custom = find_by_name(name) is None
    request_apis = (
        provider_config.api.supported_apis
        if provider_config.api is not None and spec.is_direct
        else spec.request_apis
    )
    row = {
        "id": name,
        "name": spec.label,
        "is_custom": is_custom,
        "configured": (
            bool(oauth_status["configured"])
            if oauth_status is not None
            else provider_configured_for_settings(spec, provider_config, oauth_status_reader)
        ),
        "auth_type": "oauth" if spec.is_oauth else "api_key",
        "api_key_required": provider_requires_api_key(spec),
        "api_key_hint": mask_secret_hint(provider_config.api_key),
        "api_base": provider_config.api_base,
        "default_api_base": spec.default_api_base or None,
        "model_selectable": True,
        "model_catalog": model_catalog_kind(spec),
        "request_apis": list(request_apis),
        "adapter_request_apis": list(spec.request_apis),
        "api": provider_config.api.model_dump(mode="json") if provider_config.api else None,
        "provider_api_configurable": spec.provider_api_configurable,
        "model_api_configurable": len(request_apis) > 1,
        "advanced_fields": _provider_advanced_field_names(name, spec),
        "extra_headers": request_settings.redact_request_secrets(provider_config.extra_headers),
        "extra_body": request_settings.redact_request_secrets(provider_config.extra_body),
        "extra_query": request_settings.redact_request_secrets(provider_config.extra_query),
        "balance": request_settings.redact_request_secrets(
            provider_config.balance.model_dump(mode="json") if provider_config.balance else None
        ),
        "thinking_style": provider_config.thinking_style,
        "region": getattr(provider_config, "region", None),
        "profile": getattr(provider_config, "profile", None),
        "use_proxy": provider_config.use_proxy,
    }
    if oauth_status is not None:
        row["oauth_account"] = oauth_status["account"]
        row["oauth_expires_at"] = oauth_status["expires_at"]
        row["oauth_login_supported"] = oauth_status["login_supported"]
        row["oauth_error"] = oauth_status.get("error")
    return row


def _provider_settings_rows(
    config: Config,
    selected_provider: str | None,
    oauth_status: OAuthStatusReader,
) -> list[dict[str, Any]]:
    """Return one Settings row per built-in provider."""
    return [
        _provider_settings_row(spec.name, spec, provider, oauth_status)
        for spec in PROVIDERS
        if (provider := getattr(config.providers, spec.name, None)) is not None
    ]
