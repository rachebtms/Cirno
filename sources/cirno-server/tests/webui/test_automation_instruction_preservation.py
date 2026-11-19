"""The Web UI keeps the exact task instructions that its editor submits."""

from types import SimpleNamespace

import pytest
from cirno_core.cron.service import CronService
from cirno_core.cron.types import CronSchedule
from cirno_server.webui.http.automations import AutomationsRoutes
from websockets.datastructures import Headers
from websockets.http11 import Request


@pytest.mark.parametrize(
    "message",
    ["\n  Task steps:\n    preserve: indentation\n", "  exact leading and trailing spaces  "],
)
async def test_automation_instruction_update_preserves_formatting(tmp_path, message):
    cron = CronService(tmp_path / "jobs.json")
    job = cron.add_job(
        "Report",
        CronSchedule(kind="every", every_ms=60000),
        "Original",
        session_key="websocket:report",
        origin_channel="websocket",
        origin_chat_id="report",
    )
    server = SimpleNamespace(
        cron_service=cron,
        local_trigger_store=None,
        session_manager=None,
        check_api_token=lambda request: True,
        cron_pending_job_ids=None,
        local_trigger_pending_ids=None,
    )
    routes = server.automations_routes = AutomationsRoutes(server)
    request = Request("/v0/webui/automations/update", Headers())
    request._cirno_webui_mutation_payload = {"id": job.id, "values": {"message": message}}
    response = await routes._handle_webui_automation_action(request, "update")
    assert response.status_code == 200
    persisted = CronService(cron.store_path).get_job(job.id)
    assert persisted.payload.message == message
    assert persisted.state.next_run_at_ms == job.state.next_run_at_ms


@pytest.mark.parametrize("message", ["", " \n\t"])
async def test_blank_instruction_update_is_rejected_without_replacing_existing_message(
    tmp_path, message
):
    cron = CronService(tmp_path / "jobs.json")
    job = cron.add_job(
        "Report",
        CronSchedule(kind="every", every_ms=60000),
        "Original",
        session_key="websocket:report",
        origin_channel="websocket",
        origin_chat_id="report",
    )
    server = SimpleNamespace(
        cron_service=cron,
        local_trigger_store=None,
        session_manager=None,
        check_api_token=lambda request: True,
        cron_pending_job_ids=None,
        local_trigger_pending_ids=None,
    )
    routes = server.automations_routes = AutomationsRoutes(server)
    request = Request("/v0/webui/automations/update", Headers())
    request._cirno_webui_mutation_payload = {"id": job.id, "values": {"message": message}}
    response = await routes._handle_webui_automation_action(request, "update")
    assert response.status_code == 400
    assert CronService(cron.store_path).get_job(job.id).payload.message == "Original"
