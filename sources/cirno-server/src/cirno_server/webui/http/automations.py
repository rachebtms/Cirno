"""Automations HTTP operations, isolated from transport dispatch."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from cirno_core.cron.binding import CronBindingError, binding_revision
from cirno_core.cron.session_turns import is_bound_cron_job
from cirno_core.cron.types import CronJob
from cirno_core.triggers.local_types import LocalTrigger
from cirno_server.webui.automation_chats import AutomationChat, automation_chats
from cirno_server.webui.automation_results import AutomationResultReadError, cron_run_response, trigger_run_response
from cirno_server.webui.http_utils import http_error as _http_error
from cirno_server.webui.http_utils import http_json_response as _http_json_response
from cirno_server.webui.http_utils import query_first as _query_first
from cirno_server.webui.session_automations import all_automations_payload
from loguru import logger
from websockets.http11 import Request as WsRequest
from websockets.http11 import Response

from .shared import (
    _automation_values_from_request,
    _parse_automation_update,
    _parse_local_trigger_update,
    _request_query,
)

if TYPE_CHECKING:
    from .handler import ServerHTTPHandler


class AutomationsRoutes:
    def __init__(self, server: ServerHTTPHandler) -> None:
        self.server = server

    async def _dispatch_automation_routes(
        self,
        request: WsRequest,
        got: str,
    ) -> Response | None:
        if got == "/v0/webui/automations":
            return self.server.automations_routes._handle_webui_automations(request)
        if got == "/v0/webui/automations/result":
            return await self.server.automations_routes._handle_webui_automation_result(request)
        if got == "/v0/webui/automations/chats":
            return await self.server.automations_routes._handle_webui_automation_chats(request)
        m = re.match(r"^/v0/webui/automations/(enable|disable|delete|run|update|change-chat)$", got)
        if m:
            return await self.server.automations_routes._handle_webui_automation_action(
                request, m.group(1)
            )
        return None

    def _pending_cron_job_ids_for_all(self) -> set[str]:
        if self.server.cron_service is None or self.server.cron_pending_job_ids is None:
            return set()
        pending: set[str] = set()
        for job in self.server.cron_service.list_jobs(include_disabled=True):
            session_key = job.payload.session_key
            if not session_key and job.payload.origin_channel and job.payload.origin_chat_id:
                session_key = f"{job.payload.origin_channel}:{job.payload.origin_chat_id}"
            if session_key:
                pending.update(self.server.cron_pending_job_ids(session_key))
        return pending

    def _pending_local_trigger_ids_for_all(self) -> set[str]:
        if self.server.local_trigger_store is None or self.server.local_trigger_pending_ids is None:
            return set()
        pending: set[str] = set()
        for trigger in self.server.local_trigger_store.list_triggers(include_disabled=True):
            session_key = trigger.session_key
            if not session_key and trigger.channel and trigger.chat_id:
                session_key = f"{trigger.channel}:{trigger.chat_id}"
            if session_key:
                pending.update(self.server.local_trigger_pending_ids(session_key))
        return pending

    def _pending_automation_ids_for_session(self, session_key: str) -> set[str]:
        pending: set[str] = set()
        if self.server.cron_pending_job_ids is not None:
            pending.update(self.server.cron_pending_job_ids(session_key))
        if self.server.local_trigger_pending_ids is not None:
            pending.update(self.server.local_trigger_pending_ids(session_key))
        return pending

    def _handle_webui_automations(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        pending_job_ids = self.server.automations_routes._pending_cron_job_ids_for_all()
        pending_job_ids.update(self.server.automations_routes._pending_local_trigger_ids_for_all())
        return _http_json_response(
            all_automations_payload(
                self.server.cron_service,
                local_trigger_store=self.server.local_trigger_store,
                session_manager=self.server.session_manager,
                pending_job_ids=pending_job_ids,
            )
        )

    async def _automation_chats(self, job: CronJob) -> list[AutomationChat]:
        if self.server.session_manager is None:
            return []
        return await automation_chats(
            job,
            self.server.session_manager,
            self.server.workspaces,
            self.server.channel_runtime_status() if self.server.channel_runtime_status else {},
        )

    async def _handle_webui_automation_chats(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        job_id = _query_first(_request_query(request), "id") or ""
        job = self.server.cron_service.get_job(job_id) if self.server.cron_service else None
        if job is None or not is_bound_cron_job(job):
            return _http_error(404, "automation has no movable chat")
        chats = await self.server.automations_routes._automation_chats(job)
        current = next(
            (chat for chat in chats if chat.binding.session_key == job.payload.session_key), None
        )
        return _http_json_response(
            {
                "revision": binding_revision(job),
                "current": current.public_payload() if current else None,
                "chats": [chat.public_payload() for chat in chats],
            }
        )

    async def _handle_webui_automation_result(self, request: WsRequest) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        query = _request_query(request)
        job_id = (_query_first(query, "id") or "").strip()
        try:
            run_at_ms = int(_query_first(query, "run_at_ms") or "")
        except ValueError:
            return _http_error(400, "invalid run timestamp")
        if not job_id or run_at_ms < 0:
            return _http_error(400, "invalid automation run")
        kind = _query_first(query, "kind") or "cron"
        try:
            if kind == "local_trigger":
                trigger = (
                    self.server.local_trigger_store.get(job_id)
                    if self.server.local_trigger_store
                    else None
                )
                if trigger is None or self.server.local_trigger_store is None:
                    return _http_error(404, "automation not found")
                deliveries = [item for item in trigger.run_history if item.run_at_ms == run_at_ms]
                if len(deliveries) != 1:
                    return _http_error(404, "run not found")
                response = await asyncio.to_thread(
                    trigger_run_response,
                    self.server.local_trigger_store.runs_dir,
                    trigger,
                    deliveries[0],
                )
            elif kind == "cron":
                job = self.server.cron_service.get_job(job_id) if self.server.cron_service else None
                if job is None or self.server.cron_service is None:
                    return _http_error(404, "automation not found")
                if job.payload.kind == "system_event":
                    return _http_error(403, "system automation is protected")
                runs = [item for item in job.state.run_history if item.run_at_ms == run_at_ms]
                if len(runs) != 1:
                    return _http_error(404, "run not found")
                response = await asyncio.to_thread(
                    cron_run_response,
                    self.server.cron_service.store_path.parent / "runs",
                    job,
                    runs[0],
                )
            else:
                return _http_error(400, "invalid automation kind")
        except AutomationResultReadError as exc:
            return _http_error(500, str(exc))
        except OSError:
            self.server._log.exception("Could not read automation run result")
            return _http_error(500, "Could not read run result")
        return _http_json_response({"response": response})

    async def _handle_webui_automation_action(
        self,
        request: WsRequest,
        action: str,
    ) -> Response:
        if not self.server.check_api_token(request):
            return _http_error(401, "Unauthorized")
        if self.server.cron_service is None and self.server.local_trigger_store is None:
            return _http_error(503, "automation service unavailable")

        query = _request_query(request)
        job_id = (_query_first(query, "id") or _query_first(query, "job_id") or "").strip()
        if not job_id:
            return _http_error(400, "missing automation id")
        trigger = (
            self.server.local_trigger_store.get(job_id) if self.server.local_trigger_store else None
        )
        if trigger is not None:
            return self.server.automations_routes._handle_local_trigger_action(
                request, action, trigger
            )

        if self.server.cron_service is None:
            return _http_error(404, "automation not found")
        job = self.server.cron_service.get_job(job_id)
        if job is None:
            return _http_error(404, "automation not found")
        if job.payload.kind == "system_event":
            return _http_error(403, "system automation is protected")
        if action in {"enable", "run"} and not is_bound_cron_job(job):
            return _http_error(409, "automation has no linked chat")

        if action == "enable":
            if self.server.cron_service.enable_job(job_id, enabled=True) is None:
                return _http_error(404, "automation not found")
        elif action == "disable":
            if self.server.cron_service.enable_job(job_id, enabled=False) is None:
                return _http_error(404, "automation not found")
        elif action == "delete":
            result = self.server.cron_service.remove_job(job_id)
            if result == "not_found":
                return _http_error(404, "automation not found")
            if result == "protected":
                return _http_error(403, "system automation is protected")
        elif action == "run":
            if not job.enabled:
                return _http_error(409, "automation is disabled")
            task = asyncio.create_task(self.server.cron_service.run_job(job_id, force=False))
            task.add_done_callback(self.server.automations_routes._log_automation_run_result)
        elif action == "change-chat":
            values = _automation_values_from_request(request)
            if (
                not isinstance(values, dict)
                or set(values) != {"target_id", "revision", "message"}
                or not all(isinstance(v, str) for v in values.values())
            ):
                return _http_error(400, "invalid automation chat payload")
            if job.id in self.server.automations_routes._pending_cron_job_ids_for_all():
                return _http_error(409, "automation_chat_busy")
            target = next(
                (
                    chat
                    for chat in await self.server.automations_routes._automation_chats(job)
                    if chat.id == values["target_id"]
                ),
                None,
            )
            if target is None or not target.available:
                return _http_error(409, "automation_chat_unavailable")
            if target.binding.session_key == job.payload.session_key:
                return _http_error(400, "choose a different chat")
            try:
                self.server.cron_service.change_binding(
                    job_id,
                    revision=values["revision"],
                    binding=target.binding,
                    message=values["message"],
                )
            except CronBindingError as exc:
                return _http_error(409, f"automation_chat_{exc.reason}")
            except OSError:
                logger.exception("WebUI automation chat save failed")
                return _http_error(500, "could not save the chat; try again")
        elif action == "update":
            values = _automation_values_from_request(request)
            if values is None:
                return _http_error(400, "invalid automation update payload")
            parsed = _parse_automation_update(values, current_job=job)
            if isinstance(parsed, str):
                return _http_error(400, parsed)
            try:
                result = self.server.cron_service.update_job(job_id, **parsed)
            except ValueError as exc:
                return _http_error(400, str(exc))
            if result == "not_found":
                return _http_error(404, "automation not found")
            if result == "protected":
                return _http_error(403, "system automation is protected")
        else:
            return _http_error(404, "unknown automation action")

        return self.server.automations_routes._handle_webui_automations(request)

    def _handle_local_trigger_action(
        self,
        request: WsRequest,
        action: str,
        trigger: LocalTrigger,
    ) -> Response:
        if self.server.local_trigger_store is None:
            return _http_error(503, "trigger service unavailable")
        if action == "enable":
            if self.server.local_trigger_store.enable(trigger.id, enabled=True) is None:
                return _http_error(404, "automation not found")
        elif action == "disable":
            if self.server.local_trigger_store.enable(trigger.id, enabled=False) is None:
                return _http_error(404, "automation not found")
        elif action == "delete":
            if not self.server.local_trigger_store.delete(trigger.id):
                return _http_error(404, "automation not found")
        elif action == "run":
            return _http_error(409, "local trigger requires a CLI message")
        elif action == "update":
            values = _automation_values_from_request(request)
            if values is None:
                return _http_error(400, "invalid automation update payload")
            parsed = _parse_local_trigger_update(values)
            if isinstance(parsed, str):
                return _http_error(400, parsed)
            if parsed:
                if self.server.local_trigger_store.update(trigger.id, **parsed) is None:
                    return _http_error(404, "automation not found")
        else:
            return _http_error(404, "unknown automation action")

        return self.server.automations_routes._handle_webui_automations(request)

    @staticmethod
    def _log_automation_run_result(task: asyncio.Task[bool]) -> None:
        try:
            ran = task.result()
        except Exception:
            logger.exception("WebUI automation run-now task failed")
            return
        if not ran:
            logger.warning("WebUI automation run-now task did not execute")
