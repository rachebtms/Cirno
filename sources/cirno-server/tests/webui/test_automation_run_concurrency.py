"""Run-now admission is visible before its background task first executes."""

import asyncio
import json
from types import SimpleNamespace

from websockets.datastructures import Headers
from websockets.http11 import Request

from cirno_core.cron.service import CronService
from cirno_core.cron.types import CronSchedule
from cirno_server.webui.http.automations import AutomationsRoutes


async def test_duplicate_run_now_is_rejected_and_pending_is_cleared(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def execute(job):
        calls.append(job.id)
        entered.set()
        await release.wait()

    cron = CronService(tmp_path / "jobs.json", on_job=execute)
    job = cron.add_job(
        "Report", CronSchedule(kind="every", every_ms=60_000), "Summarize",
        session_key="websocket:worker", origin_channel="websocket", origin_chat_id="worker",
    )
    server = SimpleNamespace(
        cron_service=cron, local_trigger_store=None, session_manager=None,
        check_api_token=lambda _request: True, cron_pending_job_ids=None,
        local_trigger_pending_ids=None,
    )
    routes = server.automations_routes = AutomationsRoutes(server)
    request = Request(f"/v0/webui/automations/run?id={job.id}", Headers())
    tasks = []
    try:
        response = await routes._handle_webui_automation_action(request, "run")
        assert response.status_code == 200
        tasks = list(routes._run_now_tasks.values())
        assert json.loads(response.body)["jobs"][0]["state"]["pending"] is True
        # Both requests can be processed before the first create_task gets CPU.
        duplicate = await routes._handle_webui_automation_action(request, "run")
        assert duplicate.status_code == 409
        assert routes._pending_automation_ids_for_session("websocket:worker") == {job.id}
        await asyncio.wait_for(entered.wait(), 2)
        assert calls == [job.id]
    finally:
        release.set()
        await asyncio.gather(*tasks)
        cron.stop()
    assert routes._pending_cron_job_ids_for_all() == set()
    assert len(cron.get_job(job.id).state.run_history) == 1
