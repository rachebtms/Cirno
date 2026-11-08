"""Models mutations."""

from __future__ import annotations

import json
from typing import cast
from uuid import uuid4

from cirno_core.config.loader import resolve_config_env_vars
from cirno_core.config.models import FallbackCandidate, ModelPresetConfig
from cirno_core.config.schema import Config
from cirno_core.providers.request_overrides import isolate_request_overrides
from cirno_server.webui.settings.connection_contracts import OAuthStatusReader
from cirno_server.webui.settings.contracts import (
    QueryParams,
    WebUISettingsError,
    query_first,
    query_first_alias,
)
from cirno_server.webui.settings.models.requests import (
    _parse_preset_api,
    _preset_with_request_updates,
)
from cirno_server.webui.settings.models.validation import (
    _parse_positive_int,
    _parse_temperature,
    _validate_configured_provider,
    model_display_name,
    model_display_name_exists,
)


def update_agent_model_settings(
    config: Config,
    query: QueryParams,
    *,
    oauth_status: OAuthStatusReader,
) -> bool:
    defaults = config.agents.defaults
    changed = False
    identity_changed = False

    if "model_preset" in query or "modelPreset" in query:
        preset = (query_first_alias(query, "model_preset", "modelPreset") or "").strip()
        preset_value = None if not preset or preset == "default" else preset
        if preset_value is not None and preset_value not in config.model_presets:
            raise WebUISettingsError("unknown model preset")
        if defaults.model_preset != preset_value:
            defaults.model_preset = preset_value
            changed = True

    model = query_first(query, "model")
    if model is not None:
        model = model.strip()
        if not model:
            raise WebUISettingsError("model is required")
        if defaults.model != model:
            defaults.model = model
            changed = True
            identity_changed = True

    provider = query_first(query, "provider")
    if provider is not None:
        provider = provider.strip()
        if not provider:
            raise WebUISettingsError("provider is required")
        _validate_configured_provider(config, provider, oauth_status)
        if defaults.provider != provider:
            defaults.provider = provider
            changed = True
            identity_changed = True

    context_window_tokens = _parse_positive_int(
        query_first_alias(query, "context_window_tokens", "contextWindowTokens"),
        "context_window_tokens",
    )
    if (
        context_window_tokens is not None
        and defaults.context_window_tokens != context_window_tokens
    ):
        defaults.context_window_tokens = context_window_tokens
        changed = True
    if "api" in query:
        api = _parse_preset_api(
            config, defaults.model, defaults.provider, query_first(query, "api")
        )
        if defaults.api != api:
            defaults.api = api
            changed = True
    elif identity_changed:
        defaults.api = None
    return changed


def create_model_configuration(
    config: Config,
    query: QueryParams,
    *,
    oauth_status: OAuthStatusReader,
) -> str:
    raw_name = query_first(query, "name")
    model = (query_first(query, "model") or "").strip()
    provider = (query_first(query, "provider") or "").strip()

    if not model:
        raise WebUISettingsError("model is required")
    if not provider:
        raise WebUISettingsError("provider is required")

    name = model_display_name(raw_name or "")
    if model_display_name_exists(config, name):
        raise WebUISettingsError("configuration already exists", status=409)
    _validate_configured_provider(config, provider, oauth_status)

    activate_as_primary = not config.model_presets

    base = config.resolve_preset()
    max_tokens = _parse_positive_int(
        query_first_alias(query, "max_tokens", "maxTokens"),
        "max_tokens",
    )
    context_window_tokens = _parse_positive_int(
        query_first_alias(query, "context_window_tokens", "contextWindowTokens"),
        "context_window_tokens",
    )
    temperature = _parse_temperature(query_first(query, "temperature"))
    reasoning_effort = base.reasoning_effort
    if "reasoning_effort" in query or "reasoningEffort" in query:
        reasoning_effort = (
            query_first_alias(query, "reasoning_effort", "reasoningEffort") or ""
        ).strip() or None
    identity = f"model-{uuid4().hex}"
    candidate = ModelPresetConfig(
        display_name=name,
        model=model,
        provider=provider,
        max_tokens=max_tokens if max_tokens is not None else base.max_tokens,
        context_window_tokens=(
            context_window_tokens
            if context_window_tokens is not None
            else base.context_window_tokens
        ),
        temperature=temperature if temperature is not None else base.temperature,
        reasoning_effort=reasoning_effort,
        api=_parse_preset_api(config, model, provider, query_first(query, "api")),
    )
    config.model_presets[identity] = _preset_with_request_updates(config, candidate, query)
    if activate_as_primary:
        config.agents.defaults.model_preset = identity
        config.agents.defaults.fallback_models = []
    return identity


def update_model_configuration(
    config: Config,
    query: QueryParams,
    *,
    oauth_status: OAuthStatusReader,
) -> bool:
    name = (query_first(query, "id") or "").strip()
    if not name or name == "default":
        raise WebUISettingsError("model configuration is required")

    preset = config.model_presets.get(name)
    if preset is None:
        raise WebUISettingsError("unknown model configuration")

    has_request_settings = any((preset.extra_headers, preset.extra_query, preset.extra_body))
    previous_provider = None
    if has_request_settings:
        resolved_config = resolve_config_env_vars(config)
        previous_provider = resolved_config.get_provider_name(
            preset=resolved_config.model_presets[name]
        )
    changed = False
    identity_changed = False
    new_name_value = query_first(query, "name")
    if new_name_value is not None:
        new_name = model_display_name(new_name_value)
        if model_display_name_exists(config, new_name, exclude=name):
            raise WebUISettingsError("configuration already exists", status=409)
        if new_name != (preset.display_name or name):
            preset.display_name = new_name
            changed = True

    model = query_first(query, "model")
    if model is not None:
        model = model.strip()
        if not model:
            raise WebUISettingsError("model is required")
        if preset.model != model:
            preset.model = model
            changed = True
            identity_changed = True

    provider = query_first(query, "provider")
    if provider is not None:
        provider = provider.strip()
        if not provider:
            raise WebUISettingsError("provider is required")
        _validate_configured_provider(config, provider, oauth_status)
        if preset.provider != provider:
            preset.provider = provider
            changed = True
            identity_changed = True

    context_window_tokens = _parse_positive_int(
        query_first_alias(query, "context_window_tokens", "contextWindowTokens"),
        "context_window_tokens",
    )
    if context_window_tokens is not None and preset.context_window_tokens != context_window_tokens:
        preset.context_window_tokens = context_window_tokens
        changed = True

    max_tokens = _parse_positive_int(
        query_first_alias(query, "max_tokens", "maxTokens"),
        "max_tokens",
    )
    if max_tokens is not None and preset.max_tokens != max_tokens:
        preset.max_tokens = max_tokens
        changed = True

    temperature = _parse_temperature(query_first(query, "temperature"))
    if temperature is not None and preset.temperature != temperature:
        preset.temperature = temperature
        changed = True

    if "reasoning_effort" in query or "reasoningEffort" in query:
        reasoning_effort = (
            query_first_alias(query, "reasoning_effort", "reasoningEffort") or ""
        ).strip() or None
        if preset.reasoning_effort != reasoning_effort:
            preset.reasoning_effort = reasoning_effort
            changed = True
    if "api" in query:
        api = _parse_preset_api(config, preset.model, preset.provider, query_first(query, "api"))
        if preset.api != api:
            preset.api = api
            changed = True
    elif identity_changed:
        preset.api = None
    candidate = preset
    if has_request_settings:
        resolved_config = resolve_config_env_vars(config)
        candidate = isolate_request_overrides(
            preset,
            previous_provider=previous_provider,
            provider=resolved_config.get_provider_name(preset=resolved_config.model_presets[name]),
        )
    candidate = _preset_with_request_updates(config, candidate, query)
    if candidate != preset:
        config.model_presets[name] = candidate
        changed = True
    return changed


def update_model_call_order(
    config: Config,
    query: QueryParams,
    *,
    oauth_status: OAuthStatusReader,
) -> bool:
    raw_order = query_first_alias(query, "order", "presetNames")
    if raw_order is None:
        raise WebUISettingsError("model call order is required")
    try:
        order: object = json.loads(raw_order)
    except json.JSONDecodeError:
        raise WebUISettingsError("model call order must be a JSON array") from None
    if (
        not isinstance(order, list)
        or not order
        or any(not isinstance(name, str) or not name.strip() for name in cast(list[object], order))
    ):
        raise WebUISettingsError("model call order must contain at least one preset")

    normalized_order = [cast(str, name).strip() for name in cast(list[object], order)]
    unknown = [name for name in normalized_order if name not in config.model_presets]
    if unknown:
        raise WebUISettingsError(f"unknown model preset: {unknown[0]}")

    defaults = config.agents.defaults
    fallback_models: list[FallbackCandidate] = list(normalized_order[1:])
    changed = (
        defaults.model_preset != normalized_order[0] or defaults.fallback_models != fallback_models
    )
    if changed:
        defaults.model_preset = normalized_order[0]
        defaults.fallback_models = fallback_models
    return changed


def delete_model_configuration(config: Config, query: QueryParams) -> None:
    name = (query_first(query, "id") or "").strip()
    if not name or name == "default":
        raise WebUISettingsError("model configuration is required")
    if name not in config.model_presets:
        raise WebUISettingsError("unknown model configuration")
    defaults = config.agents.defaults
    if defaults.model_preset == name:
        raise WebUISettingsError(
            "the primary model preset cannot be deleted",
            status=409,
        )
    defaults.fallback_models = [
        fallback for fallback in defaults.fallback_models if fallback != name
    ]
    if defaults.approval.model_override == name:
        defaults.approval.model_override = None
    if defaults.dream.model_override == name:
        defaults.dream.model_override = None
    del config.model_presets[name]
