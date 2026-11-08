"""Models validation."""

from __future__ import annotations

import math

from cirno_core.config.schema import Config
from cirno_server.webui.settings.connection_contracts import OAuthStatusReader
from cirno_server.webui.settings.contracts import (
    WebUISettingsError,
)
from cirno_server.webui.settings.providers.state import (
    provider_configured_for_settings,
    resolve_settings_provider,
)


def _parse_positive_int(value: str | None, field: str) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        raise WebUISettingsError(f"{field} must be an integer") from None
    if parsed <= 0:
        raise WebUISettingsError(f"{field} must be greater than zero")
    return parsed


def _parse_temperature(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        raise WebUISettingsError("temperature must be a number") from None
    if not math.isfinite(parsed) or parsed < 0 or parsed > 2:
        raise WebUISettingsError("temperature must be between 0 and 2")
    return parsed


def model_display_name(value: str) -> str:
    """Validate the editable display name of a model configuration."""
    name = value.strip()
    if not name:
        raise WebUISettingsError("configuration name is required")
    if name.casefold() == "default":
        raise WebUISettingsError("configuration name is reserved")
    if len(name) > 48:
        raise WebUISettingsError("configuration name must be 48 characters or fewer")
    if not name.isprintable():
        raise WebUISettingsError("configuration name contains unsupported characters")
    return name


def model_display_name_exists(
    config: Config,
    name: str,
    *,
    exclude: str | None = None,
) -> bool:
    normalized = name.casefold()
    return any(
        identity != exclude and (preset.display_name or identity).casefold() == normalized
        for identity, preset in config.model_presets.items()
    )


def _validate_configured_provider(
    config: Config,
    provider: str,
    oauth_status: OAuthStatusReader,
) -> None:
    if provider == "auto":
        return
    resolved_provider = resolve_settings_provider(config, provider)
    if resolved_provider is None:
        raise WebUISettingsError("unknown provider")
    spec, _, provider_config = resolved_provider
    if not provider_configured_for_settings(spec, provider_config, oauth_status):
        raise WebUISettingsError("provider is not configured")
