"""Persist learning progress independently of the task checkpoint commit."""

from __future__ import annotations

import json

from cirno_core.memory.consolidation_evidence import LearningEvidenceError
from cirno_core.memory.consolidation_receipts import index_receipt, receipt_path, write_receipt
from cirno_core.utils.file_transactions import file_write_transaction


def commit_learning(learning, plan, evidence: dict, summary: str) -> None:
    path = receipt_path(learning.repo, evidence["id"])
    with file_write_transaction([path]):
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if previous.get("status") == "completed":
            if previous["plan"] != plan.model_dump() or previous["summary"] != summary:
                raise ValueError("Archived consolidation already has a different completed plan")
            index_receipt(learning.repo, previous)
            learning.completed = True
            return
        learning.saved_items = (
            list(previous.get("saved_items", []))
            if previous.get("plan") == plan.model_dump()
            else []
        )
        record = learning_record(learning, plan, evidence, summary)
        write_receipt(learning.repo, record)

        def saved(identifier: str) -> None:
            if identifier not in learning.saved_items:
                learning.saved_items.append(identifier)
            write_receipt(learning.repo, record)

        learning.record_saved = saved
        try:
            learning._apply(plan, evidence)
            record["status"] = "completed"
            write_receipt(learning.repo, record)
        except Exception as exc:
            record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            if isinstance(exc, LearningEvidenceError):
                record["regenerate_output"] = True
            write_receipt(learning.repo, record)
            raise
        finally:
            learning.record_saved = lambda _: None
        learning.completed = True


def learning_record(learning, plan, evidence: dict, summary: str) -> dict:
    return {
        "source": evidence["id"],
        "session_key": learning.session_key,
        "project_id": learning.project_id,
        "documents": learning.documents,
        "inputs": learning.inputs,
        "known": learning.known,
        "sources": learning.sources,
        "max_updates": learning.max_updates,
        "context_chars": learning.context_chars,
        "summary": summary,
        "plan": plan.model_dump(),
        "status": "pending",
        "saved_items": learning.saved_items,
    }


def stage_learning(learning, plan, evidence: dict, summary: str) -> None:
    path = receipt_path(learning.repo, evidence["id"])
    with file_write_transaction([path]):
        if path.exists():
            return
        write_receipt(learning.repo, learning_record(learning, plan, evidence, summary))
