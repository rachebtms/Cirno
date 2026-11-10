"""Durable consolidation outcomes and model-free retries of generated learning."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from cirno_memory.repository import MemoryRepository
from cirno_core.utils.atomic_file import atomic_write_text

PREFIX = "consolidation:"


def write_receipt(repo: MemoryRepository, record: dict) -> None:
    record["at"] = datetime.now(timezone.utc).isoformat()
    path = repo.root / "consolidations" / (record["source"] + ".json")
    atomic_write_text(path, json.dumps(record, ensure_ascii=False, indent=2))
    status = {k: record[k] for k in ("source", "session_key", "status", "at")}
    status["error"] = record.get("error")
    with repo.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO maintenance VALUES(?,?)",
            (PREFIX + record["source"], json.dumps(status)),
        )


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
    from cirno_core.memory.consolidation_contract import LearningPlan
    from cirno_core.memory.consolidation_learning import ConsolidationLearning

    retried = 0
    for failure in outcomes(repo)["consolidation_failures"]:
        record = json.loads(
            (repo.root / "consolidations" / (failure["source"] + ".json")).read_text(encoding="utf-8")
        )
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
        if record.get("raw_output") is not None:
            from cirno_core.memory.consolidation_contract import split_result

            summary, plan = split_result(record["raw_output"])
        else:
            summary, plan = record["summary"], LearningPlan.model_validate(record["plan"])
        learning.apply(plan, evidence, summary)
        retried += 1
    return {"retried": retried}


def cached_output(learning, evidence: dict) -> str | None:
    """Resume an interrupted checkpoint commit without regenerating learning."""
    path = learning.repo.root / "consolidations" / (evidence["id"] + ".json")
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("raw_output") is not None:
        return None
    from cirno_core.memory.consolidation_contract import MARKER

    learning.documents, learning.inputs, learning.known = (
        record["documents"],
        record["inputs"],
        record["known"],
    )
    learning.completed = record["status"] == "completed"
    if learning.completed:
        # The JSON commit may have succeeded just before its status-index write
        # failed. Repair that index while preserving the already applied plan.
        write_receipt(learning.repo, record)
    return record["summary"] + MARKER + json.dumps(record["plan"])


def invalid_output(learning, evidence: dict, output: str, error: ValueError) -> None:
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
            "max_updates": learning.max_updates,
            "context_chars": learning.context_chars,
            "raw_output": output,
            "summary": "",
            "plan": {},
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
        },
    )
