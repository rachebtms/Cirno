"""Corrupt automation results remain distinct from missing or empty replies."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from websockets.datastructures import Headers
from websockets.http11 import Request

from cirno_core.cron.types import CronJob, CronPayload, CronRunRecord, CronSchedule
from cirno_server.webui import automation_results
from cirno_server.webui.automation_results import AutomationResultReadError, cron_run_response
from cirno_server.webui.http.automations import AutomationsRoutes


def saved_run(root: Path, body: bytes):
    root.mkdir(exist_ok=True)
    (root / "run.json").write_bytes(body)
    run = CronRunRecord(1000, "ok", 100, run_id="run")
    job = CronJob(
        id="job",
        name="Research",
        schedule=CronSchedule(kind="every", every_ms=60_000),
        payload=CronPayload(message="research", session_key="websocket:worker"),
    )
    job.state.run_history = [run]
    return job, run


@pytest.mark.parametrize("body", [b"{", b"\xff", b"[]", b"null"])
def test_selected_malformed_record_reports_its_name_without_exposing_its_contents(tmp_path, body):
    job, run = saved_run(tmp_path, body)
    with pytest.raises(AutomationResultReadError, match="run.json"):
        cron_run_response(tmp_path, job, run)
    assert (tmp_path / "run.json").read_bytes() == body


def test_oversized_record_reads_at_most_the_limit_and_one_byte(tmp_path, monkeypatch):
    limit = automation_results.MAX_RUN_RECORD_BYTES
    job, run = saved_run(tmp_path, b"x" * (limit + 100))
    read = automation_results.read_atomic_bytes
    reads = []

    def bounded_read(path, *, max_bytes):
        reads.append(max_bytes)
        return read(path, max_bytes=max_bytes)

    monkeypatch.setattr(automation_results, "read_atomic_bytes", bounded_read)
    with pytest.raises(AutomationResultReadError, match="record exceeds 2 MiB"):
        cron_run_response(tmp_path, job, run)
    assert reads == [limit + 1]


@pytest.mark.asyncio
async def test_result_http_route_reports_corrupt_record_instead_of_empty_success(tmp_path):
    job, _run = saved_run(tmp_path / "runs", b'{"private_prompt": "do not expose this",')
    server = SimpleNamespace(
        check_api_token=lambda _request: True,
        cron_service=SimpleNamespace(get_job=lambda _id: job, store_path=tmp_path / "jobs.json"),
    )
    response = await AutomationsRoutes(server)._handle_webui_automation_result(
        Request("/v0/webui/automations/result?id=job&run_at_ms=1000", Headers()),
    )
    assert response.status_code == 500
    assert b"run.json" in response.body
    assert b"do not expose this" not in response.body
