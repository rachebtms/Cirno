"""Default cron timezone must retain seasonal rules, not today's UTC offset."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from cirno_core.cron import scheduling
from cirno_core.cron.service import CronService
from cirno_core.cron.types import CronSchedule


@pytest.mark.parametrize("base,target,offset", [
    ((2026, 1, 1), (2026, 7, 1), -5),
    ((2026, 7, 1), (2027, 1, 1), -4),
])
def test_default_timezone_retains_seasonal_rules(monkeypatch, base, target, offset):
    class CurrentOffsetDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            # No host timezone/environment mutation: model the old fixed-offset
            # local tzinfo returned by datetime.now().astimezone().tzinfo.
            return SimpleNamespace(astimezone=lambda: SimpleNamespace(
                tzinfo=timezone(timedelta(hours=offset))
            ))

    monkeypatch.setattr(scheduling, "datetime", CurrentOffsetDateTime)
    monkeypatch.setattr("cirno_core.config.timezone.get_localzone_name", lambda: "America/New_York")
    zone = ZoneInfo("America/New_York")
    now = int(datetime(*base, 12, tzinfo=zone).timestamp() * 1000)
    schedule = CronSchedule(kind="cron", expr=f"0 9 1 {target[1]} *")
    expected = int(datetime(*target, 9, tzinfo=zone).timestamp() * 1000)
    assert scheduling.next_run(schedule, now) == expected
    assert scheduling.resume_next_run(schedule, None, now) == expected


@pytest.mark.parametrize("zone", ["UTC", "Asia/Shanghai", "America/New_York"])
def test_explicit_timezone_does_not_consult_host_detection(monkeypatch, zone):
    def forbidden():
        pytest.fail("Explicit cron timezone must not depend on host detection")

    monkeypatch.setattr("cirno_core.config.timezone.get_localzone_name", forbidden)
    tz = ZoneInfo(zone)
    now = int(datetime(2026, 1, 1, 8, tzinfo=tz).timestamp() * 1000)
    assert scheduling.next_run(CronSchedule(kind="cron", expr="0 9 * * *", tz=zone), now) == int(
        datetime(2026, 1, 1, 9, tzinfo=tz).timestamp() * 1000
    )


@pytest.mark.parametrize("month,target_year", [(7, 2026), (1, 2027)])
def test_created_and_reloaded_job_uses_the_same_host_timezone_rules(
    tmp_path, monkeypatch, month, target_year
):
    zone = ZoneInfo("America/New_York")
    base_month = 1 if month == 7 else 7
    now = int(datetime(2026, base_month, 1, 12, tzinfo=zone).timestamp() * 1000)
    expected = int(datetime(target_year, month, 1, 9, tzinfo=zone).timestamp() * 1000)
    monkeypatch.setattr("cirno_core.config.timezone.get_localzone_name", lambda: "America/New_York")
    monkeypatch.setattr("cirno_core.cron.service._now_ms", lambda: now)
    path = tmp_path / "jobs.json"
    service = CronService(path)
    job = service.add_job(
        "Seasonal report", CronSchedule(kind="cron", expr=f"0 9 1 {month} *"),
        "Read results", session_key="websocket:fixture", origin_channel="websocket",
        origin_chat_id="fixture",
    )
    assert job.state.next_run_at_ms == expected
    reader = CronService(path)
    loaded = reader.get_job(job.id)
    assert loaded.state.next_run_at_ms == expected
    reader._recompute_next_runs()
    assert loaded.state.next_run_at_ms == expected
    assert reader.update_job(job.id, name="Renamed report").state.next_run_at_ms == expected
