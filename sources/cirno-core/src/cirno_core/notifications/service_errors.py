"""Coalesced owner notices for failures in background service work."""

from pathlib import Path

from cirno_core.notifications.inbox import NotificationInbox


def report_service_error(state: Path | None, service: str, error: Exception, *, session_key: str | None = None) -> None:
    NotificationInbox(state).record(
        f"service:{service}:{session_key + ':' if session_key else ''}error",
        "system",
        "service_error",
        status="error",
        session_key=session_key,
        body=f"{service}: {error}",
        data={"service": service},
    )
