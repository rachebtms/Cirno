"""Offer bounded source handles and bind selected handles to framework-owned quotes."""

from __future__ import annotations

import json
from typing import Any

from cirno_core.memory.consolidation_contract import EvidenceRef, Finding, InputReview, LearningPlan
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

    def bind_finding(finding: Finding) -> Finding:
        refs = [bind(ref) for ref in finding.evidence]
        # Ordinary findings belong to the immutable batch, including when old
        # output still carries model-written archive quotations. Those quotes
        # neither locate the source nor substantiate the finding.
        # Input-based findings keep every reference: discarding an archive ref
        # there could promote mixed private evidence into shared memory.
        if not any(ref.memory_id is not None for ref in refs):
            refs = [
                ref
                for original, ref in zip(finding.evidence, refs)
                if original.source_id is not None
            ]
        return finding.model_copy(update={"evidence": refs})

    def bind_review(review: InputReview) -> InputReview:
        if review.source_id is None:
            return review
        ref = bind(EvidenceRef(source_id=review.source_id))
        if ref.memory_id is None:
            raise LearningEvidenceError("Input reviews require a supplied pending input source_id")
        return InputReview(memory_id=ref.memory_id, reason=review.reason)

    return plan.model_copy(
        update={
            "reviewed_inputs": [bind_review(review) for review in plan.reviewed_inputs],
            "memories": [bind_finding(finding) for finding in plan.memories],
            "documents": [
                edit.model_copy(update={"evidence": [bind(ref) for ref in edit.evidence]})
                for edit in plan.documents
            ],
        }
    )
