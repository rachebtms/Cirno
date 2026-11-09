"""Generate checkpoints while retaining source evidence before runtime release."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from cirno_usage.context import llm_usage_source
from loguru import logger

from cirno_core.memory.checkpoint_prompt import with_working_notes
from cirno_core.memory.store import MemoryStore
from cirno_core.memory.working_state import (
    EvidenceCheckpoint,
    bounded_handoff,
    summary_has_handoff,
    working_notes,
)
from cirno_core.providers.contracts import LLMResponse, ProviderCallContext, ProviderConversationState
from cirno_core.providers.context_budget import ContextBudget
from cirno_core.providers.conversation_state import ProviderConversationStateController
from cirno_core.providers.reasoning_history import history_policy
from cirno_core.session.model import Session
from cirno_core.session.summary import is_summary_checkpoint, session_summary_from_metadata
from cirno_core.utils.model_messages import build_assistant_message
from cirno_core.utils.prompt_templates import render_template
from cirno_core.utils.text import truncate_text_to_tokens
from cirno_core.utils.token_estimation import estimate_prompt_tokens_chain

if TYPE_CHECKING:
    from cirno_core.utils.llm_runtime import LLMRuntime

_ARCHIVE_TOOL_RESULT = (
    "Session archival does not execute tools. Use only the supplied conversation and "
    "return the requested compact checkpoint now; do not call another tool."
)


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
    ) -> str | None:
        """Generate a replacement checkpoint and optionally persist it."""
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
            return EvidenceCheckpoint(raw)

        prompt = render_template(
            "agent/consolidator_archive.md",
            strip=True,
            archive_count=len(source_messages),
        )
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
        if provider_state is not None:
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
        if input_token_budget is not None and provider_context is None:
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

        response: LLMResponse | None = None
        for attempt in range(2):
            try:
                measured = state_controller.estimate_request_context_tokens(state_messages, tool_definitions=call_tools) if state_controller is not None else None
                if measured is None:
                    measured, _ = await asyncio.to_thread(
                        estimate_prompt_tokens_chain, runtime.provider, runtime.model,
                        [*history, *request_messages] if state_controller is not None else request_messages,
                        call_tools,
                    )
                max_output = ContextBudget(runtime.context_window_tokens, runtime.generation.max_tokens).output_limit(measured)
                provider_context = replace(
                    provider_context or ProviderCallContext(),
                    context_window_tokens=runtime.context_window_tokens, input_tokens=measured,
                )
                with llm_usage_source("dream"):
                    response = await runtime.provider.chat_stream_with_retry(
                        model=runtime.model,
                        messages=request_messages,
                        tools=call_tools,
                        temperature=runtime.generation.temperature,
                        max_tokens=max_output,
                        reasoning_effort=runtime.generation.reasoning_effort,
                        provider_context=provider_context,
                    )
            except Exception:
                phase = "provider call" if attempt == 0 else "tool-call recovery"
                logger.opt(exception=True).warning(
                    "Memory archive {} failed; using raw checkpoint",
                    phase,
                )
                return await raw_fallback()
            if response.should_execute_tools is not True or attempt == 1:
                break

            logger.info(
                "Memory archive provider returned {} tool call(s); requesting checkpoint",
                len(response.tool_calls),
            )
            assistant_message = build_assistant_message(
                response.content,
                tool_calls=[call.to_openai_tool_call() for call in response.tool_calls],
                reasoning_content=response.reasoning_content,
                thinking_blocks=response.thinking_blocks,
            )
            tool_messages = [
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": _ARCHIVE_TOOL_RESULT,
                }
                for call in response.tool_calls
            ]
            request_messages = [
                *request_messages,
                assistant_message,
                *tool_messages,
            ]
            if state_controller is not None:
                state_controller.observe_response(
                    response,
                    state_messages,
                )
                state_messages.extend(
                    [
                        state_controller.project_response_message(
                            dict(assistant_message),
                            response,
                        ),
                        *[dict(message) for message in tool_messages],
                    ]
                )
                provider_context = state_controller.prepare_request(
                    state_messages,
                    context_window_tokens=runtime.context_window_tokens,
                )
                if provider_context is None or provider_context.conversation_state is None:
                    return await raw_fallback()
        assert response is not None
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
        summary = self.store.journal.normalize_entry(summary)
        if summary and (
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
        if persist and summary != "(nothing)":
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
            )
            if repository is not None and evidence:
                await asyncio.to_thread(
                    repository.record_compaction, session_key, summary, evidence["id"], project_id
                )
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
            from cirno_memory.repository import MemoryRepository

            repo = await asyncio.to_thread(MemoryRepository, self.store.workspace)
            evidence = await asyncio.to_thread(
                repo.archive_messages, messages, session.key, session.metadata.get("project_id")
            )
            summary = await asyncio.to_thread(
                self._raw_checkpoint,
                messages,
                session_key=session.key,
                previous_summary=previous_summary,
                max_tokens=runtime.generation.max_tokens,
            )
            await asyncio.to_thread(
                repo.record_compaction,
                session.key,
                summary,
                evidence["id"],
                session.metadata.get("project_id"),
            )
            return EvidenceCheckpoint(summary)

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
