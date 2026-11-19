"""Result selection uses saved run identity even when timestamps collide."""

import json
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from cirno_core.cron.types import CronJob, CronPayload, CronRunRecord, CronSchedule
from cirno_core.triggers.local_types import LocalTrigger, TriggerRunRecord
from cirno_core.utils.run_records import write_run_record
from cirno_server.webui.automation_results import trigger_run_response
from cirno_server.webui.http.automations import AutomationsRoutes
from cirno_server.webui.session_automations import serialize_automation_jobs
from websockets.datastructures import Headers
from websockets.http11 import Request


def saved_runs(root, kind):
    runs = root / "runs"
    if kind == "cron":
        job = CronJob(
            id="job",
            name="Report",
            schedule=CronSchedule(kind="every", every_ms=60000),
            payload=CronPayload(
                session_key="websocket:one", origin_channel="websocket", origin_chat_id="one"
            ),
        )
        job.state.run_history = [
            CronRunRecord(1000, "ok", 0, run_id=identifier) for identifier in ("first", "second")
        ]
        cron = SimpleNamespace(get_job=lambda _: job, store_path=root / "jobs.json")
        store = None
    else:
        job = LocalTrigger("job", "Report", True, "websocket", "one", "websocket:one")
        job.run_history = [
            TriggerRunRecord(1000, "ok", delivery_id=identifier)
            for identifier in ("first", "second")
        ]
        cron = None
        store = SimpleNamespace(get=lambda _: job, runs_dir=runs)
    for identifier in ("first", "second"):
        write_run_record(
            runs,
            identifier,
            {
                "kind": "local_trigger" if kind == "local_trigger" else "cron",
                "job_id": "job",
                "trigger_id": "job",
                "delivery_id": identifier,
                "created_at_ms": 1000,
                "session_key": "websocket:one",
                "status": "ok",
                "response": f"Result for {identifier}",
                "private_prompt": "Never expose this",
            },
        )
    return job, SimpleNamespace(
        check_api_token=lambda _: True, cron_service=cron, local_trigger_store=store
    )


@pytest.mark.parametrize("kind", ["cron", "local_trigger"])
@pytest.mark.parametrize("identifier", ["first", "second", "missing", None])
async def test_result_http_route_selects_exact_saved_identity_with_a_shared_timestamp(
    tmp_path, kind, identifier
):
    _, server = saved_runs(tmp_path, kind)
    query = {"id": "job", "kind": kind, "run_at_ms": "1000"}
    if identifier is not None:
        query["run_id"] = identifier
    response = await AutomationsRoutes(server)._handle_webui_automation_result(
        Request(f"/v0/webui/automations/result?{urlencode(query)}", Headers()),
    )
    if identifier in {"first", "second"}:
        assert response.status_code == 200
        assert json.loads(response.body) == {"response": f"Result for {identifier}"}
    else:
        assert response.status_code == 404


@pytest.mark.parametrize("kind", ["cron", "local_trigger"])
def test_run_id_is_preserved_in_the_public_history_contract(tmp_path, kind):
    job, _ = saved_runs(tmp_path, kind)
    row = serialize_automation_jobs([job], include_details=True, trigger_root=tmp_path)[0]
    assert [run["run_id"] for run in row["state"]["run_history"]] == ["first", "second"]


def test_explicit_trigger_result_ignores_unrelated_corrupt_records(tmp_path):
    trigger, _ = saved_runs(tmp_path, "local_trigger")
    (tmp_path / "runs" / "unrelated.json").write_text("{")
    assert (
        trigger_run_response(tmp_path / "runs", trigger, trigger.run_history[0])
        == "Result for first"
    )
