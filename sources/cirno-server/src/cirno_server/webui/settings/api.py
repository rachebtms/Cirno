"""Settings operations scoped to the selected instance configuration.

Domain modules validate and project configuration; these service operations
load, persist and decorate the browser response.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import cirno_server.webui.settings.models.catalog as model_catalog
import cirno_server.webui.settings.models.mutations as model_mutations
import cirno_server.webui.settings.models.payload as model_payload
import cirno_server.webui.settings.providers.mutations as provider_mutations
import cirno_server.webui.settings.providers.oauth as provider_oauth
import httpx
from cirno_core import __version__
from cirno_core.config.loader import get_config_path, load_config, save_config
from cirno_core.config.schema import Config
from cirno_server.webui.settings import capabilities as capabilities
from cirno_server.webui.settings import contracts as contracts
from cirno_server.webui.settings import runtime as runtime
from cirno_server.webui.settings import system as system
from cirno_server.webui.settings.contracts import QueryParams, WebUISettingsError
from cirno_server.webui.workspaces import write_webui_default_access_mode

if TYPE_CHECKING:
    from cirno_server.webui.settings.services import WebUIOAuthFlowRegistry


def _load_settings_config(config_path: Path | None) -> Config:
    return load_config(config_path) if config_path is not None else load_config()


def _save_settings_config(config: Config, config_path: Path | None) -> None:
    if config_path is None:
        save_config(config)
    else:
        save_config(config, config_path)


def _settings_config_path(config_path: Path | None) -> Path:
    return config_path if config_path is not None else get_config_path()


def decorate_settings_payload(
    payload: dict[str, Any],
    *,
    restart_required_sections: list[str] | None = None,
    apply_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach service restart requirements and their current apply state."""
    sections = restart_required_sections
    if sections is None:
        raw_sections: object = payload.get("restart_required_sections") or []
        sections = [
            section for section in cast(Iterable[object], raw_sections) if isinstance(section, str)
        ]
    sections = sorted(dict.fromkeys(sections))
    result = dict(payload)
    result["restart_required_sections"] = sections
    if sections:
        result["requires_restart"] = True
    else:
        result["requires_restart"] = bool(result.get("requires_restart", False))
    result["apply_state"] = apply_state or {
        "status": "pending" if result["requires_restart"] else "idle",
        "sections": sections,
    }
    return result


def settings_payload(
    *,
    requires_restart: bool = False,
    restart_required_sections: list[str] | None = None,
    apply_state: dict[str, Any] | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = _load_settings_config(config_path)
    payload: dict[str, Any] = {
        **model_payload.model_settings_payload(
            config,
            oauth_status=provider_oauth.oauth_provider_status,
        ),
        **capabilities.capability_settings_payload(
            config,
            oauth_status=provider_oauth.oauth_provider_status,
        ),
        **system.system_settings_payload(
            config,
            config_path=_settings_config_path(config_path),
            version=__version__,
        ),
        "requires_restart": requires_restart,
    }
    return decorate_settings_payload(
        payload,
        restart_required_sections=restart_required_sections,
        apply_state=apply_state,
    )


def settings_usage_payload(*, config_path: Path | None = None) -> dict[str, Any]:
    return system.settings_usage_payload(_load_settings_config(config_path))


def update_agent_settings(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = _load_settings_config(config_path)
    model_changed = model_mutations.update_agent_model_settings(
        config,
        query,
        oauth_status=provider_oauth.oauth_provider_status,
    )
    system_changed, restart_required = system.update_agent_system_settings(config, query)
    if model_changed or system_changed:
        _save_settings_config(config, config_path)
    return settings_payload(
        requires_restart=restart_required,
        config_path=config_path,
    )


def create_model_configuration(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = _load_settings_config(config_path)
    name = model_mutations.create_model_configuration(
        config,
        query,
        oauth_status=provider_oauth.oauth_provider_status,
    )
    _save_settings_config(config, config_path)
    payload = settings_payload(config_path=config_path)
    payload["created_model_preset"] = name
    return payload


def update_model_configuration(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = _load_settings_config(config_path)
    if model_mutations.update_model_configuration(
        config, query, oauth_status=provider_oauth.oauth_provider_status
    ):
        _save_settings_config(config, config_path)
    return settings_payload(config_path=config_path)


def update_model_call_order(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = _load_settings_config(config_path)
    if model_mutations.update_model_call_order(
        config,
        query,
        oauth_status=provider_oauth.oauth_provider_status,
    ):
        _save_settings_config(config, config_path)
    return settings_payload(config_path=config_path)


def delete_model_configuration(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = _load_settings_config(config_path)
    model_mutations.delete_model_configuration(config, query)
    _save_settings_config(config, config_path)
    return settings_payload(config_path=config_path)


def create_provider_settings(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = _load_settings_config(config_path)
    provider_key = provider_mutations.create_provider_settings(config, query)
    _save_settings_config(config, config_path)
    payload = settings_payload(config_path=config_path)
    payload["created_provider"] = provider_key
    return payload


def update_provider_settings(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = _load_settings_config(config_path)
    changed, restart_required = provider_mutations.update_provider_settings(config, query)
    if changed:
        _save_settings_config(config, config_path)
    return settings_payload(
        requires_restart=restart_required,
        config_path=config_path,
    )


def model_api_resolution_payload(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    return model_payload.model_api_resolution_payload(_load_settings_config(config_path), query)


def provider_models_payload(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    return model_catalog.provider_models_payload(
        _load_settings_config(config_path),
        query,
        http_get=httpx.get,
    )


def login_oauth_provider(
    query: QueryParams,
    *,
    oauth_flows: WebUIOAuthFlowRegistry,
    config_path: Path | None = None,
) -> dict[str, Any]:
    return provider_oauth.login_oauth_provider(
        _load_settings_config(config_path),
        query,
        oauth_flows=oauth_flows,
        config_path=config_path,
    )


def complete_oauth_provider(
    query: QueryParams,
    authorization_response: str | None = None,
    *,
    oauth_flows: WebUIOAuthFlowRegistry,
    config_path: Path | None = None,
) -> dict[str, Any]:
    return provider_oauth.complete_oauth_provider(
        query,
        authorization_response,
        oauth_flows=oauth_flows,
        config_path=config_path,
        settings_payload=settings_payload,
    )


def logout_oauth_provider(
    query: QueryParams,
    *,
    oauth_flows: WebUIOAuthFlowRegistry,
    config_path: Path | None = None,
) -> dict[str, Any]:
    return provider_oauth.logout_oauth_provider(
        query,
        oauth_flows=oauth_flows,
        config_path=config_path,
        settings_payload=settings_payload,
    )


def update_network_safety_settings(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = _load_settings_config(config_path)
    changed, default_access_mode = capabilities.update_network_safety_settings(
        config,
        query,
    )
    if changed:
        _save_settings_config(config, config_path)
    if default_access_mode is not None:
        try:
            write_webui_default_access_mode(default_access_mode)
        except ValueError as exc:
            raise WebUISettingsError(str(exc)) from exc
    return settings_payload(requires_restart=changed, config_path=config_path)


def update_web_search_settings(
    query: QueryParams,
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = _load_settings_config(config_path)
    changed, restart_required = capabilities.update_web_search_settings(config, query)
    if changed:
        _save_settings_config(config, config_path)
    return settings_payload(
        requires_restart=restart_required,
        config_path=config_path,
    )


def update_runtime_config_settings(
    values: dict[str, Any],
    *,
    config_path: Path | None = None,
) -> dict[str, Any]:
    config = _load_settings_config(config_path)
    changed = runtime.update_runtime_config(config, values)
    if changed:
        _save_settings_config(config, config_path)
    return settings_payload(
        requires_restart=changed,
        config_path=config_path,
    )
