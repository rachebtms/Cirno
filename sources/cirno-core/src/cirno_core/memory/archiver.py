"""Generate checkpoints while retaining source evidence before runtime release."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger
from cirno_core.utils.cancellation import shield_and_drain

from cirno_core.memory.checkpoint_prompt import with_working_notes
from cirno_core.memory.checkpoint_generation import generate_checkpoint
from cirno_core.memory.consolidation_contract import MARKER, LearningPlan, split_result
from cirno_core.memory.consolidation_result import ConsolidationCheckpoint, learning_failure
from cirno_core.memory.consolidation_preparation import prepare_learning
from cirno_core.memory.learning_commit import stage_learning
from cirno_core.memory.consolidation_receipts import invalid_output, defer_learning_for_evidence_checkpoint
from cirno_core.memory.store import MemoryStore
from cirno_core.memory.working_state import (
    EvidenceCheckpoint,
    bounded_handoff,
    summary_has_handoff,
    working_notes,
)
from cirno_core.providers.contracts import LLMResponse, ProviderConversationState
from cirno_core.providers.conversation_state import ProviderConversationStateController
from cirno_core.providers.reasoning_history import history_policy
from cirno_core.session.model import Session
from cirno_core.session.summary import is_summary_checkpoint, session_summary_from_metadata
from cirno_core.utils.text import truncate_text_to_tokens
from cirno_core.utils.token_estimation import estimate_prompt_tokens_chain

if TYPE_CHECKING:
    from cirno_core.utils.llm_runtime import LLMRuntime



class MemoryArchiver:
    """Generate transcript checkpoints and optionally journal their source.

    The archiver deliberately has no SessionManager dependency: it may read a
    captured transcript batch and, for durable sessions, append to history.jsonl,
    but it cannot mutate provider continuation state or advance a session watermark.
    """

    def __init__(
        self,
        store: MemoryStore,
        build_messages: Callable[..., list[dict[str, Any]]],
        get_tool_definitions: Callable[[Session], list[dict[str, Any]]],
        resolve_prompt_context: Callable[[Session], tuple[str | None, Path | None]] | None = None,
    ) -> None:
        self.store = store
        self._build_messages = build_messages
        self._get_tool_definitions = get_tool_definitions
        self._resolve_prompt_context = resolve_prompt_context

    def _raw_checkpoint(
        self,
        messages: list[dict[str, Any]],
        *,
        session_key: str,
        previous_summary: str | None,
        max_tokens: int,
        persist: bool = True,
    ) -> str:
        """Return a bounded raw checkpoint, optionally persisting its source."""
        raw = (
            self.store.raw_archive(messages, session_key=session_key)
            if persist
            else self.store._build_raw_checkpoint(messages)
        )
        return self._combine_raw_checkpoint(
            raw,
            previous_summary=previous_summary,
            max_tokens=max_tokens,
        )

    @staticmethod
    def _combine_raw_checkpoint(
        raw: str,
        *,
        previous_summary: str | None,
        max_tokens: int,
    ) -> str:
        """Return a bounded checkpoint that preserves prior and newly archived context."""
        token_limit = max(1, max_tokens)
        if not previous_summary:
            return bounded_handoff(raw, token_limit)

        combined = (
            "[Previous archived context]\n"
            f"{previous_summary}\n\n"
            "[Newly archived raw context]\n"
            f"{raw}"
        )
        bounded = truncate_text_to_tokens(combined, token_limit)
        if bounded == combined:
            return combined

        # Keep evidence from both sides when their full concatenation cannot fit.
        section_limit = max(1, (token_limit - 32) // 2)
        return truncate_text_to_tokens(
            "[Previous archived context]\n"
            f"{truncate_text_to_tokens(previous_summary, section_limit)}\n\n"
            "[Newly archived raw context]\n"
            f"{bounded_handoff(raw, section_limit)}",
            token_limit,
        )

    async def archive(
        self,
        source_messages: list[dict[str, Any]],
        *,
        runtime: LLMRuntime,
        session_key: str,
        history: list[dict[str, Any]],
        request_tools: list[dict[str, Any]],
        previous_summary: str | None = None,
        input_token_budget: int | None = None,
        fallback_max_tokens: int | None = None,
        provider_state: ProviderConversationState | None = None,
        persist: bool = True,
        project_id: str | None = None,
        learning_only: bool = False,
        checkpoint_text: str | None = None,
    ) -> str | None:
        """Generate a replacement checkpoint and optionally persist it."""
        # Match the immutable evidence writer's message numbering; instruction
        # prefixes stay in the request for caching, not in the source transcript.
        source_messages = [message for message in source_messages
                           if message.get("role") not in {"system", "developer"} and (learning_only or not is_summary_checkpoint(message))]
        if not source_messages:
            return None
        runtime = runtime.with_generation_overrides(
            max_tokens=min(runtime.generation.max_tokens, runtime.compaction_max_tokens),
            reasoning_effort=None
            if runtime.compaction_reasoning_effort == "inherit"
            else runtime.compaction_reasoning_effort,
        )
        from cirno_memory.repository import MemoryRepository

        repository = (
            await asyncio.to_thread(MemoryRepository, self.store.workspace) if persist else None
        )
        evidence = None
        if repository is not None:
            evidence = await asyncio.to_thread(
                repository.archive_messages,
                source_messages,
                session_key,
                project_id,
            )

        async def raw_fallback() -> str:
            if learning_only:
                raise RuntimeError("Learning regeneration produced no usable result; the existing checkpoint was not changed")
            raw = await asyncio.to_thread(
                self._raw_checkpoint,
                source_messages,
                session_key=session_key,
                previous_summary=previous_summary,
                max_tokens=(
                    fallback_max_tokens
                    if fallback_max_tokens is not None
                    else runtime.generation.max_tokens
                ),
                persist=persist,
            )
            if repository is not None and evidence:
                await asyncio.to_thread(
                    repository.record_compaction, session_key, raw, evidence["id"], project_id
                )
            failure = preparation_failure
            if learning is not None and evidence:
                try:
                    failure = await shield_and_drain(asyncio.to_thread(defer_learning_for_evidence_checkpoint, learning, evidence, raw))
                except Exception as error:
                    failure = learning_failure(evidence["id"], f"Could not retain failed learning output: {error}", {}, [])
            return EvidenceCheckpoint(raw, failure)

        learning, cached, prompt, preparation_failure = await prepare_learning(
            home=self.store.workspace, source_messages=source_messages,
            runtime=runtime, session_key=session_key, project_id=project_id,
            repository=repository, evidence=evidence, history=history,
            request_tools=request_tools, input_token_budget=input_token_budget,
            native_state=provider_state is not None, learning_only=learning_only,
        )
        if cached is None and input_token_budget is not None and input_token_budget <= 0:
            return await raw_fallback()
        if history_policy(runtime.provider, tools=request_tools, for_count=True) == "omit":
            prompt = await asyncio.to_thread(
                with_working_notes,
                prompt,
                source_messages,
                history=history,
                runtime=runtime,
                tools=request_tools,
                input_budget=input_token_budget if provider_state is None else None,
            )
        prompt_message = {"role": "user", "content": prompt}
        provider_context = None
        state_controller: ProviderConversationStateController | None = None
        state_messages: list[dict[str, Any]] = []
        call_tools = request_tools
        if provider_state is not None and cached is None:
            instruction_messages: list[dict[str, Any]] = []
            for message in history:
                if message.get("role") not in {"system", "developer"}:
                    break
                instruction_messages.append(dict(message))
            request_messages = [*instruction_messages, prompt_message]
            state_controller = ProviderConversationStateController(
                provider=runtime.provider,
                model=runtime.model,
                messages=state_messages,
                state=provider_state,
                session_id=session_key,
            )
            state_messages.append(dict(prompt_message))
            provider_context = state_controller.prepare_request(
                state_messages,
                context_window_tokens=runtime.context_window_tokens,
            )
            if provider_context is None or provider_context.conversation_state is None:
                return await raw_fallback()
            call_tools = []
        else:
            request_messages = [
                *[dict(message) for message in history],
                prompt_message,
            ]
        if cached is None and input_token_budget is not None and provider_context is None:
            estimated, source = await asyncio.to_thread(
                estimate_prompt_tokens_chain,
                runtime.provider,
                runtime.model,
                request_messages,
                call_tools,
            )
            if input_token_budget <= 0 or estimated > input_token_budget:
                logger.debug(
                    "Memory archive input does not fit for {}: {}/{} via {}; using raw checkpoint",
                    session_key,
                    estimated,
                    input_token_budget,
                    source,
                )
                return await raw_fallback()

        response: LLMResponse | None = LLMResponse(content=cached) if cached is not None else None
        if response is None:
            response = await generate_checkpoint(runtime=runtime, history=history,
                request_messages=request_messages, call_tools=call_tools,
                provider_context=provider_context, state_controller=state_controller,
                state_messages=state_messages)
        if response is None:
            return await raw_fallback()
        if response.finish_reason in {"error", "length"}:
            logger.warning(
                "Memory archive provider did not complete ({}); using raw checkpoint",
                response.finish_reason,
            )
            return await raw_fallback()
        if response.has_tool_calls is True:
            logger.warning("Memory archive provider returned tool calls; using raw checkpoint")
            return await raw_fallback()
        summary = response.content
        if not summary or not summary.strip():
            logger.warning("Memory archive provider returned no summary; using raw checkpoint")
            return await raw_fallback()
        warning = preparation_failure or (learning.deferred_failure if learning is not None else None)
        try:
            if learning_only and MARKER not in summary:
                # A heading at the beginning also has to follow the delimiter contract.
                if summary.startswith("## Memory updates\n"):
                    summary = "\n" + summary
                else:
                    raise ValueError("Learning retry did not return structured memory updates")
            summary, learning_plan = split_result(summary)
        except ValueError as error:
            if learning is not None and evidence is not None:
                warning = learning_failure(evidence["id"], f"{type(error).__name__}: {error}", {}, [])
                try:
                    await shield_and_drain(asyncio.to_thread(invalid_output, learning, evidence, summary, error))
                except Exception as receipt_error:
                    warning["error"] += f"; could not save the failed plan: {receipt_error}"
                    logger.warning("Could not retain invalid learning output for {}: {}", session_key, receipt_error)
            else:
                warning = learning_failure(evidence["id"] if evidence else "", f"{type(error).__name__}: {error}", {}, [])
            summary = summary.partition(MARKER)[0]
            learning_plan = LearningPlan()
        summary = self.store.journal.normalize_entry(summary)
        if learning_only and checkpoint_text:
            summary = checkpoint_text
        if summary and not learning_only and (
            summary.strip() == "(nothing)"
            or (working_notes(source_messages) and not summary_has_handoff(summary))
        ):
            logger.warning(
                "Memory archive omitted the working-state handoff; retaining a bounded evidence checkpoint"
            )
            return await raw_fallback()
        if not summary:
            logger.warning(
                "Memory archive provider summary was not safe to replay; using raw checkpoint"
            )
            return await raw_fallback()
        if learning is not None and evidence is not None and warning is None and not learning.completed and not learning_only:
            try:
                await shield_and_drain(asyncio.to_thread(stage_learning, learning, learning_plan, evidence, summary))
            except Exception as error:
                warning = learning_failure(evidence["id"], f"Could not retain learning plan: {error}", learning_plan.model_dump(), [])
        if not learning_only and persist and summary != "(nothing)":
            refs = [
                {
                    key: message[key]
                    for key in ("id", "message_id", "timestamp", "_meta")
                    if key in message
                }
                for message in source_messages
            ]
            if evidence:
                refs.insert(
                    0,
                    {
                        "memory_id": evidence["id"],
                        "source": evidence["source"],
                        "project_id": project_id,
                    },
                )
            await asyncio.to_thread(
                self.store.journal.append_history,
                summary,
                session_key=session_key,
                source_refs=refs,
                archive_id=evidence["id"] if evidence else None,
            )
            if repository is not None and evidence:
                await asyncio.to_thread(
                    repository.record_compaction, session_key, summary, evidence["id"], project_id
                )
        if learning is not None and evidence is not None:
            # Learning is separate from the already committed task checkpoint.
            # Accepted file writes still settle before ownership is released.
            if not learning.completed and warning is None:
                try:
                    await shield_and_drain(asyncio.to_thread(learning.apply, learning_plan, evidence, summary))
                except Exception as error:
                    logger.warning("Learning was not completed for {}; retaining the checkpoint: {}", session_key, error)
                    warning = learning_failure(evidence["id"], f"{type(error).__name__}: {error}", learning_plan.model_dump(), learning.saved_items)
        elif learning_plan.size and warning is None:
            warning = learning_failure(evidence["id"] if evidence else "", "Learning is disabled; generated memory updates were not applied", learning_plan.model_dump(), [])
        if warning:
            return EvidenceCheckpoint(summary, warning) if learning is not None and learning.raw_checkpoint else ConsolidationCheckpoint(summary, warning)
        return summary

    async def archive_session(
        self,
        session: Session,
        *,
        archive_end: int,
        runtime: LLMRuntime,
        input_token_budget: int,
    ) -> str | None:
        """Archive a captured session prefix without mutating the session."""
        messages = [
            message
            for message in session.messages[session.last_archived : archive_end]
            if not message.get("_command") and not is_summary_checkpoint(message)
        ]
        if not messages:
            return None
        session_summary = session_summary_from_metadata(
            session.metadata,
            fallback_last_active=session.updated_at,
        )
        previous_summary = session_summary["text"] if session_summary else None

        async def raw_checkpoint():
            return await self.archive(
                messages, runtime=runtime, session_key=session.key,
                history=[], request_tools=[], previous_summary=previous_summary,
                input_token_budget=0, project_id=session.metadata.get("project_id"),
            )

        if input_token_budget <= 0:
            logger.debug(
                "Memory archive has no safe input budget for {}; raw-dumping",
                session.key,
            )
            return await raw_checkpoint()
        prefix = Session(
            key=session.key,
            messages=list(session.messages[:archive_end]),
            last_archived=session.last_archived,
        )
        history = prefix.get_history(max_tokens=input_token_budget)
        archive_history = Session(
            key=session.key,
            messages=messages,
        ).get_history()
        if not archive_history or history[-len(archive_history) :] != archive_history:
            logger.debug(
                "Memory archive cannot replay the full chunk for {}; raw-dumping",
                session.key,
            )
            return await raw_checkpoint()
        channel = session.key.split(":", 1)[0] if ":" in session.key else None
        workspace: Path | None = None
        if self._resolve_prompt_context is not None:
            channel, workspace = self._resolve_prompt_context(session)
        history_messages = self._build_messages(
            history=history,
            current_message=None,
            channel=channel,
            session_summary=dict(session_summary) if session_summary else None,
            session_key=session.key,
            workspace=workspace,
        )
        tools = self._get_tool_definitions(session)
        return await self.archive(
            messages,
            runtime=runtime,
            session_key=session.key,
            history=history_messages,
            request_tools=tools,
            previous_summary=previous_summary,
            input_token_budget=input_token_budget,
            project_id=session.metadata.get("project_id"),
        )
