"""Providers oauth."""

from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cirno_core.config.loader import resolve_config_env_vars
from cirno_core.config.schema import Config
from cirno_core.providers.oauth_guidance import OAUTH_CLI_KIT_MISSING_MESSAGE
from cirno_core.providers.oauth_model_catalog import (
    invalidate_oauth_model_catalog,
)
from cirno_core.providers.registry import find_by_name
from cirno_server.webui.settings.contracts import (
    QueryParams,
    WebUISettingsError,
    parse_bool,
    query_first,
)

if TYPE_CHECKING:
    from cirno_server.webui.settings.services import (
        WebUIOAuthFlowRegistry,
    )


from cirno_server.webui.settings.connection_contracts import SettingsPayloadBuilder


def oauth_provider_status(spec: Any) -> dict[str, Any]:
    status = {"configured": False, "account": None, "expires_at": None, "login_supported": False}
    if not getattr(spec, "is_oauth", False):
        return status
    try:
        if spec.name == "openai_codex":
            from cirno_core.providers.oauth_storage import token_storage
            from oauth_cli_kit.providers import OPENAI_CODEX_PROVIDER

            read_token = token_storage("openai_codex", OPENAI_CODEX_PROVIDER.token_filename).load
        elif spec.name == "github_copilot":
            from cirno_core.providers.github_copilot_provider import get_github_copilot_login_status

            read_token = get_github_copilot_login_status
        elif spec.name == "xai_grok":
            from cirno_core.providers.xai_oauth import get_xai_oauth_login_status

            read_token = get_xai_oauth_login_status
        else:
            return status
    except ImportError as exc:
        return {**status, "error": f"OAuth support unavailable: {exc}"}

    status["login_supported"] = True
    try:
        token = read_token()
    except FileNotFoundError:
        return status
    except Exception as exc:
        # Keep other provider settings usable, but expose credential read failures.
        return {**status, "error": f"Could not read OAuth credentials: {exc}"}
    expires_at = getattr(token, "expires", None) if token else None
    now_ms = int(time.time() * 1000)
    return {
        **status,
        "configured": bool(
            token
            and token.access
            and (
                (spec.name != "github_copilot" and getattr(token, "refresh", None))
                or (expires_at and expires_at > now_ms)
            )
        ),
        "account": getattr(token, "account_id", None) if token else None,
        "expires_at": expires_at,
    }


def login_oauth_provider(
    config: Config,
    query: QueryParams,
    *,
    oauth_flows: WebUIOAuthFlowRegistry,
    config_path: Path | None,
) -> dict[str, Any]:
    provider_name = (query_first(query, "provider") or "").strip()
    if not provider_name:
        raise WebUISettingsError("provider is required")
    spec = find_by_name(provider_name)
    if spec is None or not spec.is_oauth:
        raise WebUISettingsError("unknown OAuth provider")

    if spec.name == "openai_codex":
        try:
            from cirno_core.providers.openai_codex_oauth import OpenAICodexOAuthLoginFlow
        except ImportError:
            raise WebUISettingsError(OAUTH_CLI_KIT_MISSING_MESSAGE, status=500) from None

        try:
            resolved_config = resolve_config_env_vars(config, config_path=config_path)
            proxy = resolved_config.network.resolve_proxy(
                resolved_config.providers.openai_codex.use_proxy
            )
        except ValueError as exc:
            raise WebUISettingsError(str(exc), status=400) from exc
        remote_browser_value = query_first(query, "remote_browser")
        remote_browser = (
            parse_bool(remote_browser_value, "remote_browser")
            if remote_browser_value is not None
            else False
        )
        flow = OpenAICodexOAuthLoginFlow(
            proxy=proxy,
            timeout_s=_WEBUI_OAUTH_TIMEOUT_S,
            open_browser=not remote_browser,
        )
        flow_id = secrets.token_urlsafe(24)
        try:
            oauth_flows.register(spec.name, flow_id, flow)
            flow.start()
        except Exception as exc:
            oauth_flows.remove(spec.name, flow_id, flow)
            raise WebUISettingsError(
                f"OpenAI Codex OAuth login failed: {exc}",
                status=502,
            ) from exc
        return {
            "status": "authorization_required",
            "provider": spec.name,
            "flow_id": flow_id,
            "authorization_url": flow.authorization_url,
            "expires_in": flow.remaining_seconds,
            "completion_input": "callback_url",
        }

    if spec.name == "github_copilot":
        try:
            from cirno_core.providers.github_copilot_oauth import GitHubCopilotOAuthFlow
        except ImportError:
            raise WebUISettingsError(OAUTH_CLI_KIT_MISSING_MESSAGE, status=500) from None

        # An existing token can be revoked. Expose the device prompt immediately
        # instead of waiting for approval inside a blocking CLI login request.
        oauth_flows.clear(spec.name)
        copilot_flow = GitHubCopilotOAuthFlow()
        flow_id = secrets.token_urlsafe(24)
        # Own the flow before network I/O, so logout/replacement also cancels a
        # login that is still waiting for GitHub to return its device prompt.
        try:
            oauth_flows.register(spec.name, flow_id, copilot_flow)
            copilot_flow.start()
        except Exception:
            oauth_flows.remove(spec.name, flow_id, copilot_flow)
            raise WebUISettingsError("GitHub sign-in failed. Start again.", status=502) from None
        return {
            "status": "authorization_required",
            "provider": spec.name,
            "flow_id": flow_id,
            "authorization_url": copilot_flow.authorization_url,
            "user_code": copilot_flow.user_code,
            "expires_in": copilot_flow.remaining_seconds,
            "completion_input": "device_code",
        }

    if spec.name == "xai_grok":
        from cirno_core.providers.xai_oauth import create_xai_oauth_login

        try:
            resolved_config = resolve_config_env_vars(config, config_path=config_path)
            proxy = resolved_config.network.resolve_proxy(
                resolved_config.providers.xai_grok.use_proxy
            )
        except ValueError as exc:
            raise WebUISettingsError(str(exc), status=400) from exc
        try:
            flow = create_xai_oauth_login(
                proxy=proxy,
                timeout_s=_WEBUI_OAUTH_TIMEOUT_S,
            )
        except Exception as exc:
            raise WebUISettingsError(f"xAI OAuth login failed: {exc}", status=502) from exc
        flow_id = secrets.token_urlsafe(24)
        try:
            oauth_flows.register(spec.name, flow_id, flow)
            flow.start()
        except Exception as exc:
            oauth_flows.remove(spec.name, flow_id, flow)
            raise WebUISettingsError(f"xAI OAuth login failed: {exc}", status=502) from exc
        return {
            "status": "authorization_required",
            "provider": spec.name,
            "flow_id": flow_id,
            "authorization_url": flow.authorization_url,
            "expires_in": flow.remaining_seconds,
            "completion_input": "authorization_code",
        }

    raise WebUISettingsError("OAuth login is not supported for this provider")


def complete_oauth_provider(
    query: QueryParams,
    authorization_response: str | None = None,
    *,
    oauth_flows: WebUIOAuthFlowRegistry,
    config_path: Path | None,
    settings_payload: SettingsPayloadBuilder,
) -> dict[str, Any]:
    provider_name = (query_first(query, "provider") or "").strip()
    flow_id = (query_first(query, "flow_id") or "").strip()
    spec = find_by_name(provider_name)
    if spec is None or spec.name not in {"openai_codex", "xai_grok", "github_copilot"}:
        raise WebUISettingsError("OAuth completion is not supported for this provider")
    if not flow_id:
        raise WebUISettingsError("flow_id is required")

    flow = oauth_flows.get(spec.name, flow_id)
    if flow is None:
        raise WebUISettingsError(f"{spec.label} sign-in expired. Start again.", status=410)

    cancel = query_first(query, "cancel")
    if cancel is not None and parse_bool(cancel, "cancel"):
        oauth_flows.remove(spec.name, flow_id, flow)
        return {"status": "cancelled", "provider": spec.name, "flow_id": flow_id}

    try:
        if spec.name == "openai_codex":
            from cirno_core.providers.openai_codex_oauth import OpenAICodexOAuthInputError

            try:
                token = flow.complete(authorization_response)
            except OpenAICodexOAuthInputError as exc:
                raise WebUISettingsError(str(exc), status=400) from exc
        else:
            token = flow.complete(authorization_response)
    except WebUISettingsError:
        raise
    except Exception as exc:
        oauth_flows.remove(spec.name, flow_id, flow)
        raise WebUISettingsError(
            f"{spec.label} OAuth login failed: {exc}",
            status=502,
        ) from exc
    if token is None:
        return {
            "status": "pending",
            "provider": spec.name,
            "flow_id": flow_id,
        }
    oauth_flows.remove(spec.name, flow_id, flow, cancel=False)
    if not token.access:
        raise WebUISettingsError("OAuth login failed", status=401)
    invalidate_oauth_model_catalog(spec.name)
    return settings_payload(config_path=config_path)


def logout_oauth_provider(
    query: QueryParams,
    *,
    oauth_flows: WebUIOAuthFlowRegistry,
    config_path: Path | None,
    settings_payload: SettingsPayloadBuilder,
) -> dict[str, Any]:
    provider_name = (query_first(query, "provider") or "").strip()
    if not provider_name:
        raise WebUISettingsError("provider is required")
    spec = find_by_name(provider_name)
    if spec is None or not spec.is_oauth:
        raise WebUISettingsError("unknown OAuth provider")

    if spec.name == "openai_codex":
        try:
            from cirno_core.providers.oauth_storage import token_storage
            from oauth_cli_kit.providers import OPENAI_CODEX_PROVIDER
        except ImportError:
            raise WebUISettingsError(OAUTH_CLI_KIT_MISSING_MESSAGE, status=500) from None
        oauth_flows.clear(spec.name)
        storage = token_storage("openai_codex", OPENAI_CODEX_PROVIDER.token_filename)
    elif spec.name == "github_copilot":
        try:
            from cirno_core.providers.github_copilot_provider import get_storage
        except ImportError:
            raise WebUISettingsError(OAUTH_CLI_KIT_MISSING_MESSAGE, status=500) from None
        oauth_flows.clear(spec.name)
        storage = get_storage()
    elif spec.name == "xai_grok":
        from cirno_core.providers.xai_oauth import logout_xai_oauth

        oauth_flows.clear(spec.name)
        logout_xai_oauth()
        invalidate_oauth_model_catalog(spec.name)
        return settings_payload(config_path=config_path)
    else:
        raise WebUISettingsError("OAuth logout is not supported for this provider")

    storage.delete()
    invalidate_oauth_model_catalog(spec.name)
    return settings_payload(config_path=config_path)


_OAUTH_PROXY_PROVIDERS = {"openai_codex", "xai_grok"}


_WEBUI_OAUTH_TIMEOUT_S = 600
