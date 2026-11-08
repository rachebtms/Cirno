"""Models catalog."""

from __future__ import annotations

import math
import time
from datetime import date, datetime, timezone
from typing import Any, cast

import httpx
from cirno_core.config.schema import Config
from cirno_core.providers.catalog.contracts import ProviderModelSpec, ProviderSpec
from cirno_core.providers.oauth_model_catalog import (
    get_oauth_model_catalog,
)
from cirno_server.webui.settings.connection_contracts import (
    HttpGet,
    ProviderModelMetadataPayload,
    ProviderModelRowPayload,
)
from cirno_server.webui.settings.contracts import (
    QueryParams,
    WebUISettingsError,
    query_first,
)
from cirno_server.webui.settings.providers.state import (
    _resolve_env_placeholders,
    provider_requires_api_key,
    resolve_settings_provider,
)


def model_catalog_kind(spec: Any) -> str:
    catalog = getattr(spec, "model_catalog", "auto")
    if catalog != "auto":
        return catalog
    if spec.is_oauth:
        return "unsupported"
    if spec.backend != "openai_compat" and spec.name != "minimax_anthropic":
        return "unsupported"
    if spec.is_local:
        return "local"
    if spec.is_direct:
        return "custom"
    if spec.is_gateway:
        return "catalog"
    return "official"


def _model_id_from_row(row: object) -> str | None:
    if isinstance(row, str):
        return row.strip() or None
    if not isinstance(row, dict):
        return None
    row_mapping = cast(dict[str, object], row)
    for key in ("id", "name", "model"):
        value = row_mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _model_positive_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _model_string_values(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    values: list[str] = []
    seen: set[str] = set()
    for item in cast(list[object], value):
        if not isinstance(item, str):
            return None
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            values.append(normalized)
    return values


def _model_context_window(row: object) -> int | None:
    if not isinstance(row, dict):
        return None
    row_mapping = cast(dict[str, object], row)
    for key in (
        "context_window",
        "context_length",
        "max_context_length",
        "max_model_len",
        "max_input_tokens",
    ):
        value = row_mapping.get(key)
        parsed = _model_positive_int(value)
        if parsed is not None:
            return parsed
        if isinstance(value, float) and math.isfinite(value) and value > 0:
            parsed = _model_positive_int(int(value))
            if parsed is not None:
                return parsed
    return None


def _model_shutdown_date(row: object) -> date | None:
    if not isinstance(row, dict):
        return None
    row_mapping = cast(dict[str, object], row)
    raw = row_mapping.get("shutdown_date")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _model_catalog_row_active(row: object, *, on: date | None = None) -> bool:
    """True when a provider catalog row should stay in the advisory model list."""
    shutdown = _model_shutdown_date(row)
    if shutdown is None:
        return True
    reference = on if on is not None else datetime.now(timezone.utc).date()
    return shutdown > reference


def _model_metadata_payload(
    row: object,
    metadata: ProviderModelSpec | None,
) -> ProviderModelMetadataPayload:
    row_mapping = cast(dict[str, object], row) if isinstance(row, dict) else {}
    effort = row_mapping.get("effort")
    effort_mapping = cast(dict[str, object], effort) if isinstance(effort, dict) else {}
    max_output_tokens = _model_positive_int(row_mapping.get("max_output_tokens"))
    input_modalities = _model_string_values(row_mapping.get("input_modalities"))
    output_modalities = _model_string_values(row_mapping.get("output_modalities"))
    reasoning_efforts = _model_string_values(effort_mapping.get("supported_levels"))
    raw_default = effort_mapping.get("default_level")
    default_effort = raw_default.strip() if isinstance(raw_default, str) else None

    if metadata is not None:
        if max_output_tokens is None:
            max_output_tokens = metadata.max_output_tokens
        if input_modalities is None and metadata.input_modalities:
            input_modalities = list(metadata.input_modalities)
        if output_modalities is None and metadata.output_modalities:
            output_modalities = list(metadata.output_modalities)
        if reasoning_efforts is None and metadata.reasoning_efforts:
            reasoning_efforts = list(metadata.reasoning_efforts)
        elif (
            reasoning_efforts is not None
            and "none" in metadata.reasoning_efforts
            and "none" not in reasoning_efforts
        ):
            # Catalogs may list only enabled thinking levels, not the explicit off control.
            reasoning_efforts = ["none", *reasoning_efforts]
        if default_effort not in (reasoning_efforts or []):
            default_effort = metadata.default_reasoning_effort

    payload: ProviderModelMetadataPayload = {}
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens
    if input_modalities is not None:
        payload["input_modalities"] = input_modalities
    if output_modalities is not None:
        payload["output_modalities"] = output_modalities
    if reasoning_efforts is not None:
        payload["reasoning_efforts"] = reasoning_efforts
        if default_effort and default_effort in reasoning_efforts:
            payload["default_reasoning_effort"] = default_effort
    return payload


def _model_row_payload(
    row: object,
    *,
    spec: ProviderSpec | None = None,
) -> ProviderModelRowPayload | None:
    model_id = _model_id_from_row(row)
    if not model_id:
        return None
    metadata = spec.model_metadata(model_id) if spec is not None else None
    context_window = _model_context_window(row)
    if context_window is None and metadata is not None:
        context_window = metadata.context_window
    metadata_payload = _model_metadata_payload(row, metadata)
    label: str | None = None
    description: str | None = None
    owned_by: str | None = None
    if isinstance(row, dict):
        row_mapping = cast(dict[str, object], row)
        raw_label = (
            row_mapping.get("display_name") or row_mapping.get("label") or row_mapping.get("name")
        )
        if isinstance(raw_label, str) and raw_label.strip() and raw_label.strip() != model_id:
            label = raw_label.strip()
        raw_description = row_mapping.get("description")
        if isinstance(raw_description, str) and raw_description.strip():
            description = raw_description.strip()
        raw_owner = (
            row_mapping.get("owned_by")
            or row_mapping.get("owner")
            or row_mapping.get("organization")
        )
        if isinstance(raw_owner, str) and raw_owner.strip():
            owned_by = raw_owner.strip()
    payload: ProviderModelRowPayload = {
        "id": model_id,
        "label": label,
        "owned_by": owned_by,
        "context_window": context_window,
        **metadata_payload,
    }
    if description:
        payload["description"] = description
    return payload


def _extract_model_rows(
    body: object,
    *,
    spec: ProviderSpec | None = None,
) -> list[ProviderModelRowPayload]:
    raw_rows = cast(dict[str, object], body).get("data") if isinstance(body, dict) else body
    if not isinstance(raw_rows, list):
        return []
    rows: list[ProviderModelRowPayload] = []
    seen: set[str] = set()
    for raw_row in cast(list[object], raw_rows):
        if not _model_catalog_row_active(raw_row):
            continue
        row = _model_row_payload(raw_row, spec=spec)
        if row is None or row["id"] in seen:
            continue
        seen.add(row["id"])
        rows.append(row)
    return rows


def provider_models_payload(
    config: Config,
    query: QueryParams,
    *,
    http_get: HttpGet,
) -> dict[str, Any]:
    """Fetch an advisory model list without mutating configuration."""
    provider_name = (query_first(query, "provider") or "").strip()
    if not provider_name:
        raise WebUISettingsError("provider is required")

    resolved_provider = resolve_settings_provider(config, provider_name)
    if resolved_provider is None:
        raise WebUISettingsError("unknown provider")
    spec, provider_key, provider_config = resolved_provider

    catalog_kind = model_catalog_kind(spec)
    base_payload: dict[str, Any] = {
        "provider": provider_key,
        "label": spec.label,
        "catalog_kind": catalog_kind,
        "models": [],
        "model_count": 0,
        "message": None,
        "fetched_at": time.time(),
    }
    if catalog_kind == "unsupported":
        return {
            **base_payload,
            "status": "unsupported",
            "message": "Model list is not available for this provider. Type a model ID manually.",
        }
    if catalog_kind == "builtin":
        rows = [
            {
                "id": model.id,
                "label": model.label or None,
                "description": model.description or None,
                "owned_by": spec.label,
                "context_window": model.context_window,
            }
            for model in spec.builtin_models
        ]
        return {
            **base_payload,
            "status": "available",
            "models": rows,
            "model_count": len(rows),
        }
    if catalog_kind == "hybrid":
        proxy = config.network.resolve_proxy(provider_config.use_proxy)
        catalog = get_oauth_model_catalog(
            spec.name,
            proxy=proxy,
            refresh=query_first(query, "refresh") == "1",
        )
        rows = [
            {
                "id": model.id,
                "label": model.label or None,
                "description": model.description or None,
                "owned_by": model.owned_by or spec.label,
                "context_window": model.context_window,
                "reasoning_efforts": list(model.reasoning_efforts),
                "supports_backend_search": model.supports_backend_search,
                **(
                    {
                        "api": {
                            "supported_apis": list(model.api.supported_apis),
                            "preferred_api": model.api.preferred_api,
                        },
                    }
                    if model.api is not None
                    else {}
                ),
            }
            for model in catalog.models
        ]
        return {
            **base_payload,
            "status": "available",
            "source": catalog.source,
            "error_kind": catalog.error_kind,
            "models": rows,
            "model_count": len(rows),
            "message": catalog.message,
            "fetched_at": catalog.fetched_at,
        }

    api_base = _resolve_env_placeholders(provider_config.api_base) or spec.default_api_base
    if spec.name == "openai" and not api_base:
        api_base = "https://api.openai.com/v1"
    if not api_base:
        return {
            **base_payload,
            "status": "missing_api_base",
            "message": "Configure an API base URL to load models.",
        }

    api_key = _resolve_env_placeholders(provider_config.api_key)
    if provider_requires_api_key(spec) and not api_key:
        return {
            **base_payload,
            "status": "not_configured",
            "message": "Configure this provider before loading models.",
        }

    headers = {"Accept": "application/json"}
    if api_key:
        if spec.name == "minimax_anthropic":
            headers["X-Api-Key"] = api_key
        else:
            headers["Authorization"] = f"Bearer {api_key}"

    models_url = f"{api_base.rstrip('/')}/models"
    if spec.name == "minimax_anthropic" and not api_base.rstrip("/").endswith("/v1"):
        models_url = f"{api_base.rstrip('/')}/v1/models"

    try:
        proxy = config.network.resolve_proxy(provider_config.use_proxy)
        response = http_get(
            models_url,
            headers=headers,
            timeout=10.0,
            follow_redirects=False,
            **({"proxy": proxy, "trust_env": False} if proxy else {}),
        )
        response.raise_for_status()
        rows = _extract_model_rows(response.json(), spec=spec)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in {401, 403}:
            return {
                **base_payload,
                "status": "not_configured",
                "message": "The provider rejected the configured credential.",
            }
        return {
            **base_payload,
            "status": "error",
            "message": f"Model list request failed with HTTP {status}.",
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {
            **base_payload,
            "status": "error",
            "message": f"Could not load models: {exc}",
        }

    return {
        **base_payload,
        "status": "available",
        "models": rows,
        "model_count": len(rows),
    }
