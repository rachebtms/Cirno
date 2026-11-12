"""Independent task-checkpoint and learning outcomes for delivery and recovery."""

from __future__ import annotations

from typing import Any


class ConsolidationCheckpoint(str):
    learning_failure: dict[str, Any] | None

    def __new__(cls, value: str, learning_failure: dict[str, Any] | None = None):
        result = super().__new__(cls, value)
        result.learning_failure = learning_failure
        return result


def plan_items(plan: dict) -> list[dict[str, str]]:
    items = []
    for kind, field, label in (
        ("memory", "memories", "content"),
        ("document", "documents", "path"),
        ("input", "reviewed_inputs", "memory_id"),
    ):
        items.extend(
            {"id": f"{kind}:{index}", "kind": kind, "label": str(item.get(label, ""))[:240]}
            for index, item in enumerate(plan.get(field, []))
        )
    return items


def learning_failure(source: str, error: str, plan: dict, saved: list[str]) -> dict[str, Any]:
    items = plan_items(plan)
    return {
        "source": source,
        "error": error[:1000],
        "saved": [item for item in items if item["id"] in saved],
        "pending": [item for item in items if item["id"] not in saved]
        or [
            {
                "id": "receipt" if items else "updates",
                "kind": "receipt" if items else "updates",
                "label": "",
            }
        ],
    }
