"""Models payload."""

from __future__ import annotations

from typing import Any

from cirno_core.config.loader import resolve_config_env_vars
from cirno_core.config.models import ModelPresetConfig
from cirno_core.config.schema import Config
from cirno_core.providers.catalog.models import KIMI_K3_MODELS
from cirno_core.providers.registry import create_dynamic_spec, find_by_name
from cirno_core.providers.routing import resolve_automatic_model_api
from cirno_server.webui.settings import requests as request_settings
from cirno_server.webui.settings.connection_contracts import ModelSettingsPayload, OAuthStatusReader
from cirno_server.webui.settings.contracts import (
    QueryParams,
    WebUISettingsError,
    query_first,
)
from cirno_server.webui.settings.models.requests import _PROVIDER_STRUCTURED_FIELDS
from cirno_server.webui.settings.providers.payload import (
    _provider_settings_row,
    _provider_settings_rows,
)
from cirno_server.webui.settings.providers.state import _dynamic_provider_items


def _model_call_order_state(config: Config) -> tuple[list[str], bool]:
    defaults = config.agents.defaults
    primary = defaults.model_preset
    if not primary or primary == "default" or primary not in config.model_presets:
        return [], False
    order = [primary]
    for fallback in defaults.fallback_models:
        if not isinstance(fallback, str):
            return [], False
        order.append(fallback)
    return order, True


def reasoning_effort_values_for(provider_name: str, model: str) -> list[str]:
    """Return user-facing reasoning_effort options for this provider+model."""
    spec = find_by_name(provider_name) if provider_name else None
    if spec is None:
        return list(_DEFAULT_REASONING_EFFORT_VALUES)

    model_lower = (model or "").lower()
    if model_lower.rsplit("/", 1)[-1] in KIMI_K3_MODELS:
        return ["", "low", "high", "max"]

    implicit = getattr(spec, "implicit_reasoning_models", ())
    if implicit and any(pattern in model_lower for pattern in implicit):
        return [""]

    metadata = spec.model_metadata(model)
    if metadata is not None and metadata.reasoning_efforts:
        return ["", *metadata.reasoning_efforts]

    remap = getattr(spec, "reasoning_effort_remap", ())
    if remap:
        wire_values: list[str] = []
        for _user_value, wire_value in remap:
            if wire_value and wire_value != "none" and wire_value not in wire_values:
                wire_values.append(wire_value)
        return ["", *wire_values]

    return list(_DEFAULT_REASONING_EFFORT_VALUES)


def model_api_resolution_payload(config: Config, query: QueryParams) -> dict[str, Any]:
    """Resolve a draft's automatic API using provider-owned routing rules."""
    model = (query_first(query, "model") or "").strip()
    if not model:
        raise WebUISettingsError("model is required")
    preset = ModelPresetConfig(
        model=model,
        provider=(query_first(query, "provider") or "auto").strip(),
        reasoning_effort=(query_first(query, "reasoning_effort") or "").strip() or None,
    )
    try:
        provider, api = resolve_automatic_model_api(
            resolve_config_env_vars(config.model_copy(deep=True)),
            preset=preset,
        )
    except ValueError as exc:
        raise WebUISettingsError(str(exc)) from exc
    return {"provider": provider, "api": api}


def model_settings_payload(
    config: Config,
    *,
    oauth_status: OAuthStatusReader,
) -> ModelSettingsPayload:
    defaults = config.agents.defaults
    active_preset_name = defaults.model_preset or "default"
    effective_preset = config.resolve_preset()
    provider_name = (
        config.get_provider_name(effective_preset.model, preset=effective_preset)
        or effective_preset.provider
    )
    provider = config.get_provider(effective_preset.model, preset=effective_preset)
    selected_provider = provider_name
    if effective_preset.provider != "auto":
        spec = find_by_name(effective_preset.provider)
        selected_provider = spec.name if spec else provider_name

    providers = _provider_settings_rows(config, selected_provider, oauth_status)
    for provider_key, provider_config in _dynamic_provider_items(config):
        providers.append(
            _provider_settings_row(
                provider_key,
                create_dynamic_spec(
                    provider_key,
                    display_name=provider_config.display_name or "",
                    thinking_style=provider_config.thinking_style or "",
                ),
                provider_config,
                oauth_status,
            )
        )

    model_presets = [
        {
            "id": "default",
            "name": "Default",
            "active": active_preset_name == "default",
            "is_default": True,
            "model": defaults.model,
            "provider": defaults.provider,
            "resolved_provider": config.get_provider_name(
                defaults.model,
                preset=config.resolve_default_preset(),
            ),
            "max_tokens": defaults.max_tokens,
            "context_window_tokens": defaults.context_window_tokens,
            "idle_compact_percent": defaults.idle_compact_percent,
            "idle_compact_keep_percent": defaults.idle_compact_keep_percent,
            "temperature": defaults.temperature,
            "reasoning_effort": defaults.reasoning_effort,
            "api": defaults.api.model_dump(mode="json") if defaults.api is not None else None,
            "reasoning_effort_values": reasoning_effort_values_for(
                config.get_provider_name(
                    defaults.model,
                    preset=config.resolve_default_preset(),
                )
                or defaults.provider,
                defaults.model,
            ),
        }
    ]
    for name, preset in config.model_presets.items():
        resolved_preset_provider = (
            config.get_provider_name(preset.model, preset=preset) or preset.provider
        )
        model_presets.append(
            {
                "id": name,
                "name": preset.display_name or name,
                "active": active_preset_name == name,
                "is_default": False,
                "model": preset.model,
                "provider": preset.provider,
                "resolved_provider": resolved_preset_provider,
                "max_tokens": preset.max_tokens,
                "context_window_tokens": preset.context_window_tokens,
                "idle_compact_percent": preset.idle_compact_percent,
                "idle_compact_keep_percent": preset.idle_compact_keep_percent,
                "temperature": preset.temperature,
                "reasoning_effort": preset.reasoning_effort,
                "reasoning_history": preset.reasoning_history,
                "api": preset.api.model_dump(mode="json") if preset.api is not None else None,
                **{
                    field: request_settings.redact_request_secrets(getattr(preset, field))
                    for field in _PROVIDER_STRUCTURED_FIELDS
                },
                "reasoning_effort_values": reasoning_effort_values_for(
                    resolved_preset_provider,
                    preset.model,
                ),
            }
        )

    model_call_order, model_call_order_editable = _model_call_order_state(config)
    return {
        "model_api_resolution_supported": True,
        "provider_api_configuration_supported": True,
        "agent": {
            "model": effective_preset.model,
            "provider": selected_provider,
            "resolved_provider": provider_name,
            "has_api_key": bool(provider and provider.api_key),
            "model_preset": active_preset_name,
            "max_tokens": effective_preset.max_tokens,
            "context_window_tokens": effective_preset.context_window_tokens,
            "temperature": effective_preset.temperature,
            "reasoning_effort": effective_preset.reasoning_effort,
            "reasoning_history": effective_preset.reasoning_history,
            "api": (
                effective_preset.api.model_dump(mode="json")
                if effective_preset.api is not None
                else None
            ),
            "timezone": defaults.timezone,
            "tool_status_summary_max_chars": defaults.tool_status_summary_max_chars,
        },
        "model_presets": model_presets,
        "model_request_overrides_supported": True,
        "model_call_order": model_call_order,
        "model_call_order_editable": model_call_order_editable,
        "providers": providers,
    }


_DEFAULT_REASONING_EFFORT_VALUES: tuple[str, ...] = ("", "low", "medium", "high")
