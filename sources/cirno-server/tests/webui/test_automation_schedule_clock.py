"""WebUI admission uses the scheduler's time and timezone calculation."""

import pytest
from cirno_core.cron.types import CronSchedule
from cirno_server.webui.http import shared


@pytest.mark.parametrize("outcome", [123_456_789, None, ValueError("no next occurrence")])
def test_cron_validation_uses_runtime_next_occurrence(monkeypatch, outcome):
    now = 1_790_000_000.125
    schedule = CronSchedule(kind="cron", expr="0 9 * * *")
    observed = []

    def next_run(value, now_ms):
        observed.append((value, now_ms))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(shared.time, "time", lambda: now)
    monkeypatch.setattr("cirno_core.cron.scheduling.next_run", next_run)
    # Permit either a direct import or module-qualified call in the consumer.
    if hasattr(shared, "next_run"):
        monkeypatch.setattr(shared, "next_run", next_run)
    result = shared._validate_automation_schedule(schedule)
    assert observed == [(schedule, int(now * 1000))]
    assert result == (None if isinstance(outcome, int) else "cron schedule is invalid")
