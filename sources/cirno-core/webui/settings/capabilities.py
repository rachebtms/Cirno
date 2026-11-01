"""Settings for web search and network access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, TypedDict

from cirno.agent.tools.web import SEARCH_PROVIDER_OPTIONS
from cirno.config.schema import Config
from cirno.webui.settings.contracts import (
    QueryParams,
    SettingsRequest,
    SettingsRouteResult,
    WebUISettingsError,
    parse_bool,
    query_first,
    query_first_alias,
)
from cirno.webui.settings.models import (
    OAuthStatusReader,
    mask_secret_hint,
)
from cirno.webui.workspaces import (
    read_webui_default_access_mode,
)

if TYPE_CHECKING:
    from cirno.webui.settings.services import WebUISettingsServices

SettingsOperation = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class CapabilitySettingsOperations:
    update_web_search: SettingsOperation
    update_network: SettingsOperation
    cirno_features_action: SettingsOperation


class CapabilitySettingsPayload(TypedDict):
    web_search: dict[str, Any]
    web: dict[str, Any]


_WEB_SEARCH_PROVIDER_OPTIONS = SEARCH_PROVIDER_OPTIONS
_WEB_SEARCH_PROVIDER_BY_NAME = {
    provider["name"]: provider for provider in _WEB_SEARCH_PROVIDER_OPTIONS
}


def capability_settings_payload(
    config: Config,
    *,
    oauth_status: OAuthStatusReader,
) -> CapabilitySettingsPayload:
    search = config.tools.web.search
    provider = search.provider if search.provider in _WEB_SEARCH_PROVIDER_BY_NAME else "duckduckgo"
    return {
        "web_search": {
            "provider": provider,
            "api_key_hint": mask_secret_hint(search.api_key),
            "base_url": search.base_url or None,
            "max_results": search.max_results,
            "timeout": search.timeout,
            "providers": list(_WEB_SEARCH_PROVIDER_OPTIONS),
        },
        "web": {
            "enable": config.tools.web.enable,
            "use_proxy": config.tools.web.use_proxy,
            "user_agent": config.tools.web.user_agent,
            "search": {"max_results": search.max_results, "timeout": search.timeout},
            "fetch": {"use_jina_reader": config.tools.web.fetch.use_jina_reader},
        },
    }


def update_network_safety_settings(
    config: Config,
    query: QueryParams,
) -> tuple[bool, str | None]:
    raw_allow = (
        query_first_alias(
            query,
            "webui_allow_local_service_access",
            "webuiAllowLocalServiceAccess",
        )
        or query_first_alias(
            query,
            "allow_local_preview_access",
            "allowLocalPreviewAccess",
        )
    )
    raw_default_access_mode = query_first_alias(
        query,
        "webui_default_access_mode",
        "webuiDefaultAccessMode",
    )
    if raw_allow is None and raw_default_access_mode is None:
        raise WebUISettingsError(
            "webui_allow_local_service_access or webui_default_access_mode is required"
        )

    changed = False
    if raw_allow is not None:
        allow_local = parse_bool(raw_allow, "webui_allow_local_service_access")
        if config.tools.webui_allow_local_service_access != allow_local:
            config.tools.webui_allow_local_service_access = allow_local
            changed = True

    default_access_mode: str | None = None
    if raw_default_access_mode is not None:
        default_access_mode = raw_default_access_mode.strip().lower()
        if default_access_mode == "restricted":
            default_access_mode = "default"
        if default_access_mode not in {"default", "full"}:
            raise WebUISettingsError(
                "webui_default_access_mode must be default or full"
            )
    return changed, default_access_mode


def update_web_search_settings(config: Config, query: QueryParams) -> tuple[bool, bool]:
    provider_name = (query_first(query, "provider") or "").strip().lower()
    provider_option = _WEB_SEARCH_PROVIDER_BY_NAME.get(provider_name)
    if provider_option is None:
        raise WebUISettingsError("unknown web search provider")

    search_config = config.tools.web.search
    web_config = config.tools.web
    previous_provider = search_config.provider
    changed = False
    restart_required = False

    def set_search_value(attr: str, value: object) -> None:
        nonlocal changed
        if getattr(search_config, attr) != value:
            setattr(search_config, attr, value)
            changed = True

    def set_fetch_value(attr: str, value: object) -> None:
        nonlocal changed
        if getattr(web_config.fetch, attr) != value:
            setattr(web_config.fetch, attr, value)
            changed = True

    if search_config.provider != provider_name:
        search_config.provider = provider_name
        changed = True

    credential = provider_option["credential"]
    if credential == "none":
        set_search_value("api_key", "")
        set_search_value("base_url", "")
    elif credential == "base_url":
        base_url = query_first_alias(query, "base_url", "baseUrl")
        base_url = base_url.strip() if base_url is not None else None
        if not base_url and previous_provider == provider_name and search_config.base_url:
            base_url = search_config.base_url
        if not base_url:
            raise WebUISettingsError("base_url is required")
        set_search_value("base_url", base_url)
        set_search_value("api_key", "")
    elif credential in {"api_key", "optional_api_key"}:
        raw_api_key = query_first_alias(query, "api_key", "apiKey")
        api_key = raw_api_key.strip() if raw_api_key is not None else None
        if api_key is None and previous_provider == provider_name and search_config.api_key:
            api_key = search_config.api_key
        if credential == "api_key" and not api_key:
            raise WebUISettingsError("api_key is required")
        set_search_value("api_key", api_key or "")
        set_search_value("base_url", "")
    else:
        raise WebUISettingsError("unknown web search credential type")

    max_results = query_first_alias(query, "max_results", "maxResults")
    if max_results is not None:
        try:
            parsed = int(max_results)
        except ValueError:
            raise WebUISettingsError("max_results must be an integer") from None
        if parsed < 1 or parsed > 10:
            raise WebUISettingsError("max_results must be between 1 and 10")
        set_search_value("max_results", parsed)

    timeout = query_first(query, "timeout")
    if timeout is not None:
        try:
            parsed_timeout = int(timeout)
        except ValueError:
            raise WebUISettingsError("timeout must be an integer") from None
        if parsed_timeout < 1 or parsed_timeout > 120:
            raise WebUISettingsError("timeout must be between 1 and 120")
        set_search_value("timeout", parsed_timeout)

    use_jina_reader = query_first_alias(query, "use_jina_reader", "useJinaReader")
    if use_jina_reader is not None:
        previous_jina_reader = web_config.fetch.use_jina_reader
        set_fetch_value("use_jina_reader", parse_bool(use_jina_reader, "use_jina_reader"))
        if web_config.fetch.use_jina_reader != previous_jina_reader:
            restart_required = True
    return changed, restart_required


def network_safety_payload(config: Config) -> dict[str, Any]:
    """Return the network-related fields embedded in the advanced DTO."""
    return {
        "webui_allow_local_service_access": config.tools.webui_allow_local_service_access,
        "allow_local_preview_access": config.tools.webui_allow_local_service_access,
        "webui_default_access_mode": read_webui_default_access_mode(),
        "private_service_protection_enabled": True,
        "ssrf_whitelist_count": len(config.tools.ssrf_whitelist),
    }


class CapabilitySettingsHandler:
    """Handle capability commands after transport authentication and decoding."""

    def __init__(self, settings: WebUISettingsServices, logger: Any) -> None:
        self.settings = settings
        self.logger = logger

    async def handle(self, action: str, request: SettingsRequest, operations: CapabilitySettingsOperations) -> SettingsRouteResult:
        mutation = {
            "web-search-update": (operations.update_web_search, "browser"),
            "network-update": (operations.update_network, "runtime"),
        }.get(action)
        if mutation is None:
            return SettingsRouteResult.failure(404, "unknown settings action")
        operation, section = mutation
        try:
            payload = self.settings.mutate(operation, request.query)
        except WebUISettingsError as exc:
            return SettingsRouteResult.failure(exc.status, exc.message)
        return SettingsRouteResult.success(payload, decorate_restart=True, restart_section=section)


    def _allow_feature_package_install(self, request: SettingsRequest) -> bool:
        if request.local_browser:
            return True
        try:
            return bool(
                self.settings.config.load().tools.webui_allow_remote_package_install
            )
        except Exception:
            self.logger.exception("failed to load remote package install policy")
            return False
