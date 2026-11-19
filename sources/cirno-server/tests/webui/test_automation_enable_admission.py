"""The Web UI does not acknowledge a one-shot that cannot run."""

from dataclasses import asdict
from types import SimpleNamespace

from cirno_core.cron.service import CronService
from cirno_core.cron.types import CronSchedule
from cirno_server.webui.http.automations import AutomationsRoutes
from websockets.datastructures import Headers
from websockets.http11 import Request


async def test_expired_one_shot_enable_returns_actionable_error_without_changing_job(
    tmp_path, monkeypatch
):
    now = 1_900_000_000_000
    monkeypatch.setattr("cirno_core.cron.service._now_ms", lambda: now)
    cron = CronService(tmp_path / "jobs.json")
    job = cron.add_job(
        "Reminder",
        CronSchedule(kind="at", at_ms=now + 1000),
        "Send report",
        session_key="websocket:report",
        origin_channel="websocket",
        origin_chat_id="report",
    )
    cron.enable_job(job.id, False)
    before = asdict(cron.get_job(job.id))
    now += 2000
    server = SimpleNamespace(
        cron_service=cron,
        local_trigger_store=None,
        session_manager=None,
        check_api_token=lambda request: True,
        cron_pending_job_ids=None,
        local_trigger_pending_ids=None,
    )
    routes = server.automations_routes = AutomationsRoutes(server)
    request = Request("/v0/webui/automations/enable", Headers())
    request._cirno_webui_mutation_payload = {"id": job.id}
    response = await routes._handle_webui_automation_action(request, "enable")
    assert response.status_code == 400
    assert b"future occurrence" in response.body
    assert asdict(CronService(cron.store_path).get_job(job.id)) == before


async def test_update_time_expiring_after_http_validation_preserves_original_job(
    tmp_path, monkeypatch
):
    from cirno_server.webui.http import shared

    now = 1_900_000_000_000
    monkeypatch.setattr(shared.time, "time", lambda: now / 1000)
    monkeypatch.setattr("cirno_core.cron.service._now_ms", lambda: now)
    cron = CronService(tmp_path / "jobs.json")
    job = cron.add_job(
        "Original",
        CronSchedule(kind="every", every_ms=60000),
        "Original instructions",
        session_key="websocket:report",
        origin_channel="websocket",
        origin_chat_id="report",
    )
    before = asdict(cron.get_job(job.id))
    actions = cron._action_path.read_bytes()
    validate = shared._validate_automation_schedule

    def expire(schedule):
        nonlocal now
        error = validate(schedule)
        assert error is None
        now += 2000
        return None

    monkeypatch.setattr(shared, "_validate_automation_schedule", expire)
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
    request._cirno_webui_mutation_payload = {
        "id": job.id,
        "values": {
            "name": "Rejected name",
            "message": "Rejected instructions",
            "schedule": {"kind": "at", "at_ms": now + 1000},
        },
    }
    response = await routes._handle_webui_automation_action(request, "update")
    assert response.status_code == 400
    assert b"future occurrence" in response.body
    assert asdict(CronService(cron.store_path).get_job(job.id)) == before
    assert cron._action_path.read_bytes() == actions
