"""Models requests."""

from __future__ import annotations

import json

from cirno_core.config.models import ModelAPIConfig, ModelPresetConfig
from cirno_core.config.schema import Config
from cirno_core.providers.routing import resolve_model_api
from cirno_server.webui.settings import requests as request_settings
from cirno_server.webui.settings.contracts import (
    QueryParams,
    WebUISettingsError,
    query_first_alias,
    query_has_alias,
)
from cirno_server.webui.settings.providers.state import resolve_settings_provider


def _preset_with_request_updates(
    config: Config,
    preset: ModelPresetConfig,
    query: QueryParams,
) -> ModelPresetConfig:
    from cirno_core.providers.routing import resolve_provider_route

    updates = {
        snake: request_settings.restore_request_secrets(
            request_settings.parse_request_object(query, snake, camel),
            getattr(preset, snake),
        )
        for snake, camel in (
            ("extra_headers", "extraHeaders"),
            ("extra_query", "extraQuery"),
            ("extra_body", "extraBody"),
        )
        if query_has_alias(query, snake, camel)
    }
    for snake, camel in (
        ("idle_compact_percent", "idleCompactPercent"),
        ("idle_compact_keep_percent", "idleCompactKeepPercent"),
    ):
        if query_has_alias(query, snake, camel):
            raw = query_first_alias(query, snake, camel)
            try:
                value = float(raw) if raw and raw.strip() else None
            except ValueError:
                raise WebUISettingsError(f"{snake} must be a percentage") from None
            if value is not None and not 0 <= value <= 100:
                raise WebUISettingsError(f"{snake} must be between 0 and 100")
            updates[snake] = value
    history = query_first_alias(query, "reasoning_history", "reasoningHistory")
    if history is not None and history not in {"auto", "preserve", "omit"}:
        raise WebUISettingsError("Choose Automatic, Preserve or Omit for reasoning history")
    percentage_updates = {
        key: updates.pop(key) for key in tuple(updates) if key.startswith("idle_compact_")
    }
    # The provider validator already owns structured JSON validation and safe errors.
    validated = request_settings.validate_request_config(None, updates)
    candidate = preset.model_copy(
        update={**{key: getattr(validated, key) for key in updates}, **percentage_updates}
    )
    for key in ("image_input", "video_input"):
        if key in query:
            try:
                value = json.loads(query_first_alias(query, key, key) or "null")
            except ValueError:
                raise WebUISettingsError(f"{key} must be true, false or null") from None
            if value is not None and not isinstance(value, bool):
                raise WebUISettingsError(f"{key} must be true, false or null")
            candidate = candidate.model_copy(update={key: value})
    if history is not None:
        candidate = candidate.model_copy(update={"reasoning_history": history})
    if candidate.reasoning_history == "omit":
        route = resolve_provider_route(config, preset=candidate)
        if route.spec is not None and route.spec.name == "deepseek":
            raise WebUISettingsError(
                "DeepSeek tool requests require reasoning history. Select Automatic or Preserve."
            )
    trigger = (
        candidate.idle_compact_percent
        if candidate.idle_compact_percent is not None
        else config.agents.defaults.idle_compact_percent
    )
    keep = (
        candidate.idle_compact_keep_percent
        if candidate.idle_compact_keep_percent is not None
        else config.agents.defaults.idle_compact_keep_percent
    )
    if trigger > 0 and keep >= trigger:
        raise WebUISettingsError(
            "Retention percentage must be below the compaction trigger percentage"
        )
    if any(getattr(candidate, key) for key in _PROVIDER_STRUCTURED_FIELDS):
        try:
            resolve_provider_route(config, preset=candidate)
        except ValueError as exc:
            raise WebUISettingsError(str(exc)) from None
    return candidate


def _parse_preset_api(
    config: Config,
    model: str,
    provider: str,
    raw: str | None,
) -> ModelAPIConfig | None:
    if not raw:
        return None
    try:
        value: object = json.loads(raw)
        api = ModelAPIConfig.model_validate(value) if value is not None else None
    except ValueError:
        raise WebUISettingsError(
            "api must declare supportedApis and a preferredApi from that list",
        ) from None
    if api is None:
        return None
    preset = ModelPresetConfig(model=model, provider=provider)
    provider_name = config.get_provider_name(model, preset=preset) or provider
    entry = resolve_settings_provider(config, provider_name)
    if entry is None:
        raise WebUISettingsError("unknown provider")
    spec, _, provider_config = entry
    try:
        resolve_model_api(spec, provider_config, api)
    except ValueError as exc:
        raise WebUISettingsError(str(exc)) from None
    return api


_PROVIDER_STRUCTURED_FIELDS = ("extra_headers", "extra_body", "extra_query")
