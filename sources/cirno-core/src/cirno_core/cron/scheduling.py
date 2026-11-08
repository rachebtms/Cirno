"""Scheduling shared by creation, edits, timer execution and restart recovery."""

from datetime import datetime

from cirno_core.cron.types import CronSchedule


def next_run(schedule: CronSchedule, now_ms: int) -> int | None:
    """Compute next run time in ms."""
    if schedule.kind == "at":
        return schedule.at_ms if schedule.at_ms and schedule.at_ms > now_ms else None

    if schedule.kind == "every":
        if not schedule.every_ms or schedule.every_ms <= 0:
            return None
        # Next interval from now
        return now_ms + schedule.every_ms

    if schedule.kind == "cron" and schedule.expr:
        from zoneinfo import ZoneInfo

        from croniter import croniter

        tz = ZoneInfo(schedule.tz) if schedule.tz else datetime.now().astimezone().tzinfo
        base_dt = datetime.fromtimestamp(now_ms / 1000, tz=tz)
        return int(croniter(schedule.expr, base_dt).get_next(datetime).timestamp() * 1000)

    return None


def resume_next_run(schedule: CronSchedule, persisted_ms: int | None, now_ms: int) -> int | None:
    """Return the next run for a reloaded job, keeping a pending interval run.

    ``every`` schedules are relative to the previous run, so recomputing them
    from ``now`` on every startup postpones the job by a full interval each
    time the gateway restarts. A persisted next run is kept while it is still
    in the future and no more than one interval away; anything else falls back
    to :func:`next_run`.
    """
    if (
        schedule.kind == "every"
        and schedule.every_ms
        and schedule.every_ms > 0
        and persisted_ms is not None
        and now_ms < persisted_ms <= now_ms + schedule.every_ms
    ):
        return persisted_ms
    return next_run(schedule, now_ms)


def validate_schedule(schedule: CronSchedule) -> None:
    """Validate schedule fields that would otherwise create non-runnable jobs."""
    if schedule.tz and schedule.kind != "cron":
        raise ValueError("tz can only be used with cron schedules")
    if schedule.kind == "every" and (schedule.every_ms is None or schedule.every_ms <= 0):
        raise ValueError("every schedule requires a positive 'every_ms'")

    if schedule.kind == "cron":
        if not schedule.expr or not schedule.expr.strip():
            raise ValueError("cron schedule requires a non-empty 'expr'")
        try:
            from croniter import croniter

            croniter(schedule.expr)
        except ValueError as exc:
            raise ValueError(f"invalid cron expression '{schedule.expr}': {exc}") from None
        if schedule.tz:
            try:
                from zoneinfo import ZoneInfo

                ZoneInfo(schedule.tz)
            except KeyError:
                raise ValueError(f"unknown timezone '{schedule.tz}'") from None
