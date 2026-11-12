"""Offer bounded source handles and bind selected handles to framework-owned quotes."""

from __future__ import annotations

import json
from typing import Any

from cirno_core.memory.consolidation_contract import EvidenceRef, LearningPlan
from cirno_core.memory.consolidation_evidence import LearningEvidenceError
from cirno_core.runtime.context import public_history_message


def text_excerpt(message: dict[str, Any]) -> str:
    content = public_history_message(message).get("content", "")
    if isinstance(content, str):
        return content[:400]
    if isinstance(content, list):
        return next(
            (
                block["text"][:400]
                for block in content
                if isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
                and block["text"].strip()
            ),
            "",
        )
    return ""


def archive_sources(
    messages: list[dict[str, Any]], budget: int
) -> tuple[list[str], dict[str, dict]]:
    """Keep the initial user objective and recent evidence within the tail budget."""
    first_user = next(
        (i for i, message in enumerate(messages) if message.get("role") == "user"), None
    )
    order = ([first_user] if first_user is not None else []) + [
        i for i in reversed(range(len(messages))) if i != first_user
    ]
    selected = {}
    for index in order:
        quote = text_excerpt(messages[index])
        if not quote.strip():
            continue
        source_id = f"archive:{index}"
        block = json.dumps(
            {"source_id": source_id, "role": messages[index].get("role"), "excerpt": quote},
            ensure_ascii=False,
        )
        if len(block) + 1 <= budget:
            selected[index] = (source_id, block, {"message": index, "quote": quote})
            budget -= len(block) + 1
    rows = [selected[index] for index in sorted(selected)]
    return [row[1] for row in rows], {row[0]: row[2] for row in rows}


def bind_plan(plan: LearningPlan, sources: dict[str, dict]) -> LearningPlan:
    """Do not use model-written quotations for a selected framework source handle."""

    def bind(ref: EvidenceRef) -> EvidenceRef:
        if ref.source_id is None:
            return ref
        if ref.source_id not in sources:
            raise LearningEvidenceError(
                "Learning evidence source_id was not supplied in this batch"
            )
        return EvidenceRef.model_validate(sources[ref.source_id])

    return plan.model_copy(
        update={
            "memories": [
                finding.model_copy(update={"evidence": [bind(ref) for ref in finding.evidence]})
                for finding in plan.memories
            ],
            "documents": [
                edit.model_copy(update={"evidence": [bind(ref) for ref in edit.evidence]})
                for edit in plan.documents
            ],
        }
    )
