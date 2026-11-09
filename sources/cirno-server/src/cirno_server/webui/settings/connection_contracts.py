"""Provider and model settings payloads and operation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, NotRequired, TypedDict

import httpx

OAuthStatusReader = Callable[[Any], dict[str, Any]]


SettingsPayloadBuilder = Callable[..., dict[str, Any]]


HttpGet = Callable[..., httpx.Response]


SettingsOperation = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ConnectionSettingsOperations:
    update_agent: SettingsOperation
    create_model: SettingsOperation
    update_model: SettingsOperation
    delete_model: SettingsOperation
    update_call_order: SettingsOperation
    update_provider: SettingsOperation
    create_provider: SettingsOperation
    provider_models: SettingsOperation
    model_api: SettingsOperation
    oauth_login: SettingsOperation
    oauth_complete: SettingsOperation
    oauth_logout: SettingsOperation


class ModelSettingsPayload(TypedDict):
    agent: dict[str, Any]
    model_presets: list[dict[str, Any]]
    model_call_order: list[str]
    model_call_order_editable: bool
    model_capability_testing_supported: bool
    model_api_resolution_supported: bool
    provider_api_configuration_supported: bool
    model_request_overrides_supported: bool
    providers: list[dict[str, Any]]


class ProviderModelMetadataPayload(TypedDict, total=False):
    max_output_tokens: int
    input_modalities: list[str]
    output_modalities: list[str]
    reasoning_efforts: list[str]
    default_reasoning_effort: str


class ProviderModelRowPayload(ProviderModelMetadataPayload):
    id: str
    label: str | None
    owned_by: str | None
    context_window: int | None
    description: NotRequired[str]
