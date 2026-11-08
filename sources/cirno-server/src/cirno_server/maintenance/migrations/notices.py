"""Publish each completed migration once, including recovery after interrupted startup."""

import json
from pathlib import Path

from cirno_core.notifications.inbox import NotificationInbox


def publish_completed(root: Path, state: Path) -> None:
    if (root / "notified").exists():
        return
    report = json.loads((root / "report.json").read_text())
    summary = report["summary"] if "summary" in report else (
        f"Imported {report['conversations']} conversations from {report['stores']} stores. "
        "Automation state now belongs to the instance."
    )
    NotificationInbox(state).record(
        "migration:" + root.name, "system", "migration",
        body=(f"Cirno updated from {report['from']} to {report['to']}. "
              f"{summary} "
              f"Original data: {root / 'originals'}"),
        data=report,
    )
    (root / "notified").touch(mode=0o600)
