"""Report acknowledged learning writes, separately from proposed updates."""

from __future__ import annotations

import json
from typing import Literal, TypedDict

from cirno_memory.repository import MemoryRepository

from cirno_core.memory.consolidation_receipts import receipt_path
from cirno_core.memory.consolidation_result import plan_items
from cirno_core.utils.file_transactions import file_write_transaction


class LearningRetryReport(TypedDict):
    source: str | None
    mode: Literal["pending", "none", "replay", "regenerate"]
    outcome: Literal["running", "completed", "no_updates", "not_found", "incomplete"]
    model_called: bool
    requested: list[dict[str, str]]
    saved: list[dict[str, str]]
    previously_saved: list[dict[str, str]]
    pending: list[dict[str, str]]


def empty_report(source: str | None = None) -> LearningRetryReport:
    return {
        "source": source,
        "mode": "pending",
        "outcome": "running",
        "model_called": False,
        "requested": [],
        "saved": [],
        "previously_saved": [],
        "pending": [],
    }


def completed_report(
    repo: MemoryRepository,
    original: dict,
    *,
    mode: Literal["replay", "regenerate"],
    model_called: bool,
) -> LearningRetryReport:
    path = receipt_path(repo, original["source"])
    with file_write_transaction([path]):
        current = json.loads(path.read_text(encoding="utf-8"))
    items = plan_items(current.get("plan", {}))
    saved_ids = current.get("saved_items", [])
    # Completed legacy receipts predate per-item acknowledgements.
    if current["status"] == "completed" and "saved_items" not in current:
        saved_ids = [item["id"] for item in items]
    saved = [item for item in items if item["id"] in saved_ids]
    pending = [item for item in items if item["id"] not in saved_ids]
    before = plan_items(original.get("plan", {}))
    previous_ids = original.get("saved_items", [])
    return {
        "source": original["source"],
        "mode": mode,
        "model_called": model_called,
        "outcome": (
            "incomplete"
            if current["status"] != "completed"
            else "completed"
            if items
            else "no_updates"
        ),
        "requested": [item for item in before if item["id"] not in previous_ids],
        "saved": saved,
        "previously_saved": [item for item in before if item["id"] in previous_ids],
        "pending": pending,
    }
