"""Providers state."""

from __future__ import annotations

import os
import re
from typing import Any

from cirno_core.config.providers import ProviderConfig
from cirno_core.config.schema import Config
from cirno_core.providers.catalog.contracts import ProviderSpec
from cirno_core.providers.registry import create_dynamic_spec, find_by_name
from cirno_server.webui.settings.connection_contracts import OAuthStatusReader
from cirno_server.webui.settings.providers.oauth import _OAUTH_PROXY_PROVIDERS


def mask_secret_hint(secret: str | None) -> str | None:
    if not secret:
        return None
    if len(secret) <= 8:
        return "••••"
    return f"{secret[:4]}••••{secret[-4:]}"


def _resolve_env_placeholders(value: str | None) -> str | None:
    if not value:
        return None

    def replace(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1), "")

    resolved = _ENV_REF_RE.sub(replace, value).strip()
    return resolved or None


def provider_requires_api_key(spec: Any) -> bool:
    if spec.name == "azure_openai":
        return False
    if spec.is_oauth:
        return False
    if spec.is_local or spec.is_direct:
        return False
    return True


def provider_requires_api_base(spec: Any) -> bool:
    if spec.name == "azure_openai":
        return True
    return bool(spec.backend == "openai_compat" and spec.is_direct and not spec.default_api_base)


def provider_configured_for_settings(
    spec: Any,
    provider_config: Any,
    oauth_status: OAuthStatusReader,
) -> bool:
    if spec.is_oauth:
        return bool(oauth_status(spec)["configured"])
    if provider_requires_api_base(spec):
        return bool(provider_config.api_base)
    if provider_requires_api_key(spec):
        return bool(provider_config.api_key)
    return bool(
        provider_config.api_key
        or provider_config.api_base
        or getattr(provider_config, "region", None)
        or getattr(provider_config, "profile", None)
    )


def _dynamic_provider_items(config: Config) -> list[tuple[str, ProviderConfig]]:
    model_extra = config.providers.model_extra or {}
    return [
        (name, provider_config)
        for name, provider_config in model_extra.items()
        if isinstance(provider_config, ProviderConfig)
    ]


def resolve_settings_provider(
    config: Config,
    provider_name: str,
) -> tuple[ProviderSpec, str, ProviderConfig] | None:
    spec = find_by_name(provider_name)
    if spec is not None:
        provider_config = getattr(config.providers, spec.name, None)
        if isinstance(provider_config, ProviderConfig):
            return spec, spec.name, provider_config
        return None

    normalized = provider_name.replace("-", "_")
    for extra_name, provider_config in _dynamic_provider_items(config):
        if provider_name == extra_name or normalized == extra_name.replace("-", "_"):
            return (
                create_dynamic_spec(
                    extra_name,
                    display_name=provider_config.display_name or "",
                    thinking_style=provider_config.thinking_style or "",
                ),
                extra_name,
                provider_config,
            )
    return None


def _provider_advanced_field_names(name: str, spec: Any) -> list[str]:
    fields: list[str] = []
    if spec.backend in {"openai_compat", "anthropic"}:
        fields.append("extra_headers")
    if spec.backend in {"openai_compat", "anthropic", "bedrock", "openai_codex", "xai_grok"}:
        fields.append("extra_body")
    if spec.backend in {"openai_compat", "anthropic"}:
        fields.extend(("extra_query", "use_proxy"))
    if spec.name in _OAUTH_PROXY_PROVIDERS and "use_proxy" not in fields:
        fields.append("use_proxy")
    if spec.backend == "bedrock":
        fields.extend(("region", "profile"))
    if find_by_name(name) is None:
        fields.append("thinking_style")
    return fields


_ENV_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
