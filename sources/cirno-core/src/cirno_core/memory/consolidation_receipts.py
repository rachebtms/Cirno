"""Durable consolidation outcomes and model-free retries of generated learning."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cirno_memory.repository import MemoryRepository
from cirno_core.memory.consolidation_contract import output_error, output_sections
from cirno_core.memory.consolidation_result import learning_failure
from cirno_core.utils.atomic_file import atomic_write_text
from cirno_core.utils.file_transactions import file_write_transaction

PREFIX = "consolidation:"


def receipt_path(repo: MemoryRepository, source: str) -> Path:
    return repo.root / "consolidations" / (source + ".json")


def index_receipt(repo: MemoryRepository, record: dict) -> None:
    status = {k: record[k] for k in ("source", "session_key", "status", "at")}
    status["error"] = record.get("error")
    if record.get("status") == "failed":
        report = learning_failure(record["source"], record.get("error", ""), record.get("plan", {}), record.get("saved_items", []))
        if "plan" not in record:
            report.update({key: record[key] for key in ("saved", "pending") if key in record})
        status.update(report)
    with repo.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO maintenance VALUES(?,?)",
            (PREFIX + record["source"], json.dumps(status)),
        )


def write_receipt(repo: MemoryRepository, record: dict) -> None:
    record["at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_text(
        receipt_path(repo, record["source"]), json.dumps(record, ensure_ascii=False, indent=2)
    )
    index_receipt(repo, record)


def outcomes(repo: MemoryRepository) -> dict:
    with repo.connect() as db:
        rows = db.execute(
            "SELECT value FROM maintenance WHERE key LIKE ? ORDER BY json_extract(value,'$.at') DESC LIMIT 10",
            (PREFIX + "%",),
        ).fetchall()
        failures = db.execute(
            "SELECT value FROM maintenance WHERE key LIKE ? AND json_extract(value,'$.status')='failed' ORDER BY json_extract(value,'$.at') DESC LIMIT 10",
            (PREFIX + "%",),
        ).fetchall()
        count = db.execute(
            "SELECT count(*) FROM maintenance WHERE key LIKE ? AND json_extract(value,'$.status')='failed'",
            (PREFIX + "%",),
        ).fetchone()[0]
    return {
        "last_consolidation": json.loads(rows[0][0]) if rows else None,
        "consolidation_failures": [json.loads(row[0]) for row in failures],
        "consolidation_failed": count,
    }


def retry_learning(repo: MemoryRepository) -> dict:
    """Replay already-generated output; this endpoint never makes an API call."""
    with repo.connect() as db:
        rows = db.execute(
            "SELECT value FROM maintenance WHERE key LIKE ? AND json_extract(value,'$.status')='failed' ORDER BY json_extract(value,'$.at') ASC LIMIT 11",
            (PREFIX + "%",),
        ).fetchall()
    retried, failures = 0, []
    for row in rows[:10]:
        failure = json.loads(row[0])
        with file_write_transaction([receipt_path(repo, failure["source"])]):
            try:
                _retry_one(repo, failure)
            except Exception as exc:
                error = output_error(exc)
                failures.append({"source": failure["source"], "error": error})
                # Rotate failed attempts so an invalid batch cannot starve older
                # recoverable work. Keep the original receipt for inspection.
                failure.update(at=datetime.now(timezone.utc).isoformat(), error=error)
                index_receipt(repo, failure)
            else:
                retried += 1
    result = {"retried": retried}
    if failures:
        result["failures"] = failures
    if len(rows) > 10:
        result["has_more"] = True
    return result


def _retry_one(repo: MemoryRepository, failure: dict) -> None:
    from cirno_core.memory.consolidation_contract import LearningPlan
    from cirno_core.memory.consolidation_learning import ConsolidationLearning

    record = json.loads(receipt_path(repo, failure["source"]).read_text(encoding="utf-8"))
    if record["status"] == "completed":
        index_receipt(repo, record)
        return
    evidence = repo.read(record["source"], maintenance=True)
    source = (repo.home / evidence["source"]).resolve()
    if source.parent != repo.root / "sources":
        raise ValueError("Consolidation source is not an archived conversation")
    with source.open(encoding="utf-8") as stream:
        messages = [json.loads(line) for line in stream]
    learning = ConsolidationLearning(
        repo.home,
        messages,
        session_key=record["session_key"],
        project_id=record.get("project_id"),
        context_chars=record["context_chars"],
        max_updates=record["max_updates"],
    )
    learning.documents, learning.inputs, learning.known = (
        record["documents"],
        record["inputs"],
        record["known"],
    )
    learning.sources = record.get("sources", {})
    if record.get("raw_output") is not None:
        from cirno_core.memory.consolidation_contract import split_result

        if not record["raw_output"]:
            raise ValueError("No learning output was generated; use /consolidate retry")
        summary, plan = split_result(record["raw_output"])
    else:
        summary, plan = record["summary"], LearningPlan.model_validate(record["plan"])
    learning.apply(plan, evidence, summary)


def cached_output(learning, evidence: dict) -> str | None:
    """Resume an interrupted checkpoint commit without regenerating learning."""
    path = receipt_path(learning.repo, evidence["id"])
    with file_write_transaction([path]):
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") == "failed" and record.get("summary"):
            learning.deferred_failure = learning_failure(record["source"], record.get("error", ""), record.get("plan", {}), record.get("saved_items", []))
            learning.raw_checkpoint = record.get("evidence_checkpoint", False)
            return record["summary"]
        if record.get("raw_output") is not None:
            return None
        from cirno_core.memory.consolidation_contract import MARKER

        learning.documents, learning.inputs, learning.known = (
            record["documents"],
            record["inputs"],
            record["known"],
        )
        learning.sources = record.get("sources", {})
        learning.completed = record["status"] == "completed"
        if learning.completed:
            # The JSON commit may have succeeded just before its status-index write
            # failed. Repair that index while preserving the already applied plan.
            write_receipt(learning.repo, record)
        return record["summary"] + MARKER + json.dumps(record["plan"])


def invalid_output(learning, evidence: dict, output: str, error: ValueError, *, summary: str | None = None) -> None:
    """Keep an invalid generated plan inspectable without claiming it was saved."""
    write_receipt(
        learning.repo,
        {
            "source": evidence["id"],
            "session_key": learning.session_key,
            "project_id": learning.project_id,
            "documents": learning.documents,
            "inputs": learning.inputs,
            "known": learning.known,
            "sources": learning.sources,
            "max_updates": learning.max_updates,
            "context_chars": learning.context_chars,
            "raw_output": output,
            "summary": summary if summary is not None else output_sections(output)[0],
            "plan": {},
            "status": "failed",
            "error": output_error(error),
        },
    )


def defer_learning_for_evidence_checkpoint(learning, evidence: dict, summary: str) -> dict | None:
    path = receipt_path(learning.repo, evidence["id"])
    with file_write_transaction([path]):
        if not path.exists():
            invalid_output(learning, evidence, "", ValueError("No complete learning output; an evidence checkpoint retained task continuity"), summary=summary)
        record = json.loads(path.read_text())
        if record["status"] == "completed":
            return None
        record.update(summary=summary, evidence_checkpoint=True)
        write_receipt(learning.repo, record)
        return learning_failure(record["source"], record.get("error", ""), record.get("plan", {}), record.get("saved_items", []))
