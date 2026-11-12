"""Explicit, owning-session recovery of one deferred learning batch at a time."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from cirno_core.memory.consolidation_evidence import needs_new_output
from cirno_core.memory.consolidation_receipts import PREFIX, _retry_one, receipt_path
from cirno_core.memory.consolidation_result import learning_failure
from cirno_core.memory.consolidation_retry_report import completed_report, empty_report
from cirno_core.session.model import Session
from cirno_memory.repository import MemoryRepository
from cirno_core.utils.cancellation import shield_and_drain

if TYPE_CHECKING:
    from cirno_core.memory.archiver import MemoryArchiver
    from cirno_core.utils.llm_runtime import LLMRuntime


async def retry_session_learning(
    archiver: MemoryArchiver, session: Session, runtime: LLMRuntime, source: str | None = None
) -> dict[str, Any]:
    if not runtime.consolidation_learn:
        raise ValueError("Learning during consolidation is disabled in Settings")
    repo = await asyncio.to_thread(MemoryRepository, archiver.store.workspace)

    def pending():
        with repo.connect() as db:
            rows = db.execute(
                "SELECT value FROM maintenance WHERE key LIKE ? AND json_extract(value,'$.status')='failed' "
                "AND json_extract(value,'$.session_key')=? ORDER BY json_extract(value,'$.at') ASC",
                (PREFIX + "%", session.key),
            ).fetchall()
        for row in rows:
            item = json.loads(row[0])
            if source is None or item["source"] == source:
                record = json.loads(receipt_path(repo, item["source"]).read_text())
                if record.get("project_id") == session.metadata.get("project_id"):
                    return record
        return None

    record = await asyncio.to_thread(pending)
    if record is None:
        report = empty_report(source)
        report.update(mode="none", outcome="not_found")
        return {"retried": 0, "learning_retry": report}
    original = record
    model_called = False

    def request_started():
        nonlocal model_called
        model_called = True

    async def finish(*, mode, failure=None):
        report = await asyncio.to_thread(
            completed_report,
            repo,
            original,
            mode=mode,
            model_called=model_called,
        )
        result = {
            "retried": 0 if failure or report["outcome"] == "incomplete" else 1,
            "source": original["source"],
            "learning_retry": report,
        }
        if failure:
            result["learning_failure"] = failure
        return result

    try:
        await shield_and_drain(asyncio.to_thread(_retry_one, repo, record))
        return await finish(mode="replay")
    except Exception as error:
        record = await asyncio.to_thread(
            lambda: json.loads(receipt_path(repo, record["source"]).read_text())
        )
        if record.get("saved_items") or not (
            record.get("raw_output") is not None or needs_new_output(record)
        ):
            return await finish(
                mode="replay",
                failure=learning_failure(
                    record["source"],
                    str(error),
                    record.get("plan", {}),
                    record.get("saved_items", []),
                ),
            )

    def original_messages():
        evidence = repo.read(
            record["source"], session_key=session.key, project_id=session.metadata.get("project_id")
        )
        path = (repo.home / evidence["source"]).resolve()
        if path.parent != repo.root / "sources":
            raise ValueError("Learning retry requires an archived conversation source")
        with path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream]

    messages = await asyncio.to_thread(original_messages)
    history = Session(key=session.key, messages=messages).get_history()
    channel, workspace = (
        archiver._resolve_prompt_context(session)
        if archiver._resolve_prompt_context
        else (session.key.split(":", 1)[0], None)
    )
    history = archiver._build_messages(
        history=history,
        current_message=None,
        channel=channel,
        session_key=session.key,
        workspace=workspace,
    )
    try:
        result = await archiver.archive(
            messages,
            runtime=runtime,
            session_key=session.key,
            history=history,
            request_tools=archiver._get_tool_definitions(session),
            project_id=session.metadata.get("project_id"),
            learning_only=True,
            on_model_request=request_started,
            checkpoint_text=record.get("summary")
            or "Learning-only recovery; no task checkpoint replacement.",
        )
    except Exception as error:
        from cirno_core.memory.consolidation_receipts import write_receipt
        from cirno_core.utils.file_transactions import file_write_transaction

        error_message = f"{type(error).__name__}: {error}"

        def retain_error():
            path = receipt_path(repo, record["source"])
            with file_write_transaction([path]):
                current = json.loads(path.read_text())
                if current["status"] == "completed":
                    return None
                current["error"] = error_message
                write_receipt(repo, current)
                return learning_failure(
                    current["source"],
                    current["error"],
                    current.get("plan", {}),
                    current.get("saved_items", []),
                )

        failure = await shield_and_drain(asyncio.to_thread(retain_error))
        return await finish(mode="regenerate", failure=failure)

    failure = getattr(result, "learning_failure", None)
    return await finish(mode="regenerate", failure=failure)
