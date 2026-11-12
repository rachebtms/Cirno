"""Prepare optional learning without making it a prerequisite for checkpointing."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cirno_memory.repository import MemoryRepository

from cirno_core.memory.consolidation_learning import ConsolidationLearning
from cirno_core.memory.consolidation_receipts import cached_output, receipt_path, write_receipt
from cirno_core.memory.consolidation_result import learning_failure
from cirno_core.utils.cancellation import shield_and_drain
from cirno_core.utils.prompt_templates import render_template
from cirno_core.utils.token_estimation import estimate_prompt_tokens_chain
from cirno_core.utils.llm_runtime import LLMRuntime


async def prepare_learning(
    *,
    home: Path,
    source_messages: list[dict[str, Any]],
    runtime: LLMRuntime,
    session_key: str,
    project_id: str | None,
    repository: MemoryRepository | None,
    evidence: dict | None,
    history: list[dict[str, Any]],
    request_tools: list[dict[str, Any]],
    input_token_budget: int | None,
    native_state: bool,
    learning_only: bool,
) -> tuple[ConsolidationLearning | None, str | None, str, dict | None]:
    prompt = render_template(
        "agent/consolidator_archive.md", strip=True, archive_count=len(source_messages)
    )
    if repository is None or not runtime.consolidation_learn:
        return None, None, prompt, None
    assert evidence is not None
    learning = None
    try:
        learning = await asyncio.to_thread(
            ConsolidationLearning,
            home,
            source_messages,
            session_key=session_key,
            project_id=project_id,
            context_chars=runtime.consolidation_context_chars,
            max_updates=runtime.consolidation_max_updates,
        )
        cached = (
            await shield_and_drain(asyncio.to_thread(cached_output, learning, evidence))
            if not learning_only
            else None
        )
        if input_token_budget is not None and input_token_budget <= 0:
            return learning, cached, prompt, None
        instruction = render_template(
            "agent/consolidation_learning.md",
            strip=True,
            archive_count=len(source_messages),
            learning_context="",
            max_updates=runtime.consolidation_max_updates,
        )
        if learning_only:
            instruction = (
                "The task checkpoint is already retained. Retry ONLY durable learning from the archived batch. "
                "Do not rewrite or output a task checkpoint. Return only the exact heading ## Memory updates "
                "and one JSON object ({} if there are no supported updates).\n"
                + instruction.partition("## Durable learning in this same response")[2]
            )
        if input_token_budget is not None and not native_state:
            baseline, _ = await asyncio.to_thread(
                estimate_prompt_tokens_chain,
                runtime.provider,
                runtime.model,
                [*history, {"role": "user", "content": instruction}],
                request_tools,
            )
            learning.context_chars = min(
                learning.context_chars, max(0, input_token_budget - baseline - 256)
            )
        references = (
            await asyncio.to_thread(learning.context)
            if cached is None
            else "(using saved learning plan)"
        )
        return learning, cached, instruction + "\n" + references, None
    except Exception as error:
        if learning_only:
            raise  # Explicit recovery cannot claim learning succeeded without preparation.
        failure = learning_failure(
            evidence["id"], f"Learning preparation failed: {type(error).__name__}: {error}", {}, []
        )

        def retain():
            path = receipt_path(repository, evidence["id"])
            if not path.exists():
                write_receipt(
                    repository,
                    {
                        "source": evidence["id"],
                        "session_key": session_key,
                        "project_id": project_id,
                        "documents": {},
                        "inputs": {},
                        "known": {},
                        "sources": {},
                        "context_chars": runtime.consolidation_context_chars,
                        "max_updates": runtime.consolidation_max_updates,
                        "summary": "",
                        "raw_output": "",
                        "plan": {},
                        "status": "failed",
                        "error": failure["error"],
                    },
                )

        try:
            await shield_and_drain(asyncio.to_thread(retain))
        except Exception as receipt_error:
            failure["error"] += f"; could not retain learning retry state: {receipt_error}"
        return None, None, prompt, failure
