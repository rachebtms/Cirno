"""Skills HTTP operations, isolated from transport dispatch."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from cirno_core.utils.cancellation import shield_and_drain
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response

from cirno_server.webui.http_utils import http_error as _http_error
from cirno_server.webui.http_utils import http_json_response as _http_json_response
from cirno_server.webui.http_utils import parse_query as _parse_query
from cirno_server.webui.http_utils import query_first as _query_first
from cirno_server.webui.skills_api import (
    SkillManagementError,
    delete_webui_skill,
    set_webui_skill_enabled,
    webui_skill_detail_payload,
    webui_skills_payload,
)
from cirno_server.webui.skills_marketplace import (
    SkillsMarketplaceError,
    install_marketplace_skill,
    marketplace_skill_trends,
    search_marketplace_skills,
    trending_marketplace_skills,
)

from .shared import _request_query

if TYPE_CHECKING:
    from .handler import ServerHTTPHandler


class SkillsRoutes:
    def __init__(self, server: ServerHTTPHandler) -> None:
        self.server = server
        self._state_lock = asyncio.Lock()

    async def _load_webui_skills(self) -> dict[str, Any]:
        return await asyncio.to_thread(
            webui_skills_payload,
            self.server.skills_workspace_path,
            disabled_skills=set(self.server.disabled_skills),
            home_path=self.server.settings.home_path,
            config_path=self.server.settings.config.path,
        )

    async def _handle_webui_skills(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        return _http_json_response(await self.server.skills_routes._load_webui_skills())

    async def _handle_webui_skills_search(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        params = _parse_query(request.path)
        query = _query_first(params, "q") or ""
        provider = _query_first(params, "provider") or "all"
        try:
            payload = await search_marketplace_skills(
                query,
                self.server.skills_workspace_path,
                provider=provider,
                home_path=self.server.settings.home_path,
                config_path=self.server.settings.config.path,
            )
        except SkillsMarketplaceError as exc:
            return _http_error(exc.status, exc.message)
        except Exception:
            self.server._log.exception("skills marketplace search failed")
            return _http_error(500, "skills marketplace search failed")
        return _http_json_response(payload)

    async def _handle_webui_skills_trending(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        provider = _query_first(_parse_query(request.path), "provider") or "all"
        try:
            payload = await trending_marketplace_skills(
                self.server.skills_workspace_path,
                provider=provider,
                home_path=self.server.settings.home_path,
                config_path=self.server.settings.config.path,
            )
        except SkillsMarketplaceError as exc:
            return _http_error(exc.status, exc.message)
        except Exception:
            self.server._log.exception("skills marketplace trending lookup failed")
            return _http_error(500, "skills marketplace trending lookup failed")
        return _http_json_response(payload)

    async def _handle_webui_skill_trends(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        skill_ids = _parse_query(request.path).get("id", [])
        try:
            payload = await marketplace_skill_trends(skill_ids)
        except Exception:
            self.server._log.exception("skills.sh trend history lookup failed")
            return _http_error(500, "skills.sh trend history lookup failed")
        return _http_json_response(payload)

    async def _handle_webui_skill_install(
        self,
        request: WsRequest,
    ) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        if self.server._skill_install_lock.locked():
            return _http_error(409, "another skill installation is already in progress")

        query = _request_query(request)
        provider = _query_first(query, "provider") or "skills_sh"
        source = _query_first(query, "source") or ""
        skill_id = _query_first(query, "skill") or ""
        version = _query_first(query, "version") or ""
        async with self.server._skill_install_lock:
            try:
                action = await install_marketplace_skill(
                    source,
                    skill_id,
                    self.server.skills_workspace_path,
                    provider=provider,
                    home_path=self.server.settings.home_path,
                    config_path=self.server.settings.config.path,
                    version=version,
                )
            except SkillsMarketplaceError as exc:
                return _http_error(exc.status, exc.message)
            except Exception:
                self.server._log.exception("skill installation failed")
                return _http_error(500, "skill installation failed")
        return _http_json_response(
            {
                **(await self.server.skills_routes._load_webui_skills()),
                "last_action": action,
            }
        )

    async def _handle_webui_skill_update(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        query = _request_query(request)
        name = _query_first(query, "name") or ""
        raw_enabled = (_query_first(query, "enabled") or "").lower()
        if raw_enabled not in {"true", "false"}:
            return _http_error(400, "enabled must be true or false")
        try:
            action = await self._mutate_skill(name, enabled=raw_enabled == "true")
        except SkillManagementError as exc:
            return _http_error(exc.status, exc.message)
        return _http_json_response(
            {
                **(await self.server.skills_routes._load_webui_skills()),
                "last_action": action,
            }
        )

    async def _handle_webui_skill_delete(
        self,
        request: WsRequest,
    ) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        name = _query_first(_request_query(request), "name") or ""
        try:
            action = await self._mutate_skill(name)
        except SkillManagementError as exc:
            return _http_error(exc.status, exc.message)
        return _http_json_response(
            {
                **(await self.server.skills_routes._load_webui_skills()),
                "last_action": action,
            }
        )

    async def _mutate_skill(self, name: str, *, enabled: bool | None = None) -> dict[str, Any]:
        async def finish():
            async with self._state_lock:
                # Keep thread mutations private until the accepted commit and
                # its runtime publication can be observed together on the loop.
                disabled = set(self.server.disabled_skills)
                def write(config_path):
                    if enabled is None:
                        return delete_webui_skill(
                            self.server.skills_workspace_path, name, disabled_skills=disabled,
                            config_path=config_path, home_path=self.server.settings.home_path,
                        )
                    return set_webui_skill_enabled(
                        self.server.skills_workspace_path, name, enabled=enabled, disabled_skills=disabled,
                        config_path=config_path, home_path=self.server.settings.home_path,
                    )
                action = await asyncio.to_thread(self.server.settings.config.run_serialized, write)
                self.server.disabled_skills.clear()
                self.server.disabled_skills.update(disabled)
                self._apply_skill_state()
                return action
        return await shield_and_drain(finish())

    def _apply_skill_state(self) -> None:
        if self.server.skill_state_action is not None:
            self.server.skill_state_action(set(self.server.disabled_skills))

    async def _handle_webui_skill_detail(self, request: WsRequest, raw_name: str) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")

        name = unquote(raw_name)
        if not name or "/" in name or "\\" in name:
            return _http_error(400, "invalid skill name")
        payload = await asyncio.to_thread(
            webui_skill_detail_payload,
            self.server.skills_workspace_path,
            name,
            disabled_skills=set(self.server.disabled_skills),
            home_path=self.server.settings.home_path,
            config_path=self.server.settings.config.path,
        )
        if payload is None:
            return _http_error(404, "skill not found")
        return _http_json_response(payload)
