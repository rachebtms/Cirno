"""Coordinate model request preparation, budget admission and compaction."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from cirno_core.agent.governance.budget import (
    input_budget,
    request_extends_measured,
    request_measurement,
)
from cirno_core.agent.governance.compaction import RequestCompactor
from cirno_core.agent.governance.contracts import ModelRequestState
from cirno_core.agent.governance.messages import prepare_messages
from cirno_core.agent.governance.preparation import PromptPreparation
from cirno_core.providers.contracts import (
    ProviderCallContext,
)
from loguru import logger


def request_snapshot(
    messages: list[dict[str, Any]],
    tool_definitions: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    return deepcopy(messages), deepcopy(tool_definitions)


class ContextGovernor:
    def __init__(self) -> None:
        self.preparation = PromptPreparation()
        self.compaction = RequestCompactor(self.preparation)

    async def accept_request(
        self,
        state: ModelRequestState,
        model_messages: list[dict[str, Any]],
        *,
        raw_boundary: int,
    ) -> None:
        """Advance accepted history on the loop after copying its payload."""
        accepted = await self.preparation.run(deepcopy, model_messages)
        state.compaction.accepted_messages = accepted
        state.compaction.raw_accepted_boundary = raw_boundary

    async def prepare_request(
        self,
        state: ModelRequestState,
        messages: list[dict[str, Any]],
        *,
        tool_definitions: list[dict[str, Any]] | None,
        transcript: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], ProviderCallContext | None]:
        """Prepare or compact and record the exact provider payload."""
        prepared = await self.preparation.run(
            prepare_messages,
            state.config,
            messages,
        )
        model_messages: list[dict[str, Any]] | None = prepared
        supplemental_messages: list[dict[str, Any]] | None = None
        request_context_tokens = None
        if transcript is not None:
            if tool_definitions is None:
                model_messages = None
                supplemental_messages = [prepared[-1]]
            request_context_tokens = await self.preparation.run(
                state.conversation.estimate_request_context_tokens,
                transcript,
                model_messages=model_messages,
                supplemental_messages=supplemental_messages,
                tool_definitions=tool_definitions,
            )
        usage_matches_messages = (
            state.messages is not None
            and prepared == state.messages
            and tool_definitions == state.tool_definitions
        )
        usage_prefixes_messages = (
            state.messages is not None
            and tool_definitions == state.tool_definitions
            and request_extends_measured(state.messages, prepared)
        )
        measurement = await self.preparation.run(
            request_measurement,
            state.config,
            prepared,
            state.usage,
            usage_matches_messages=usage_matches_messages,
            usage_prefixes_messages=usage_prefixes_messages,
            tool_definitions=tool_definitions,
            request_context_tokens=request_context_tokens,
            measured_messages=state.messages,
        )
        state.input_tokens = measurement[0]
        limit = input_budget(state.config)
        state.checkpoint_needed = (
            limit > 0
            and limit * state.config.checkpoint_reminder_percent / 100 <= measurement[0] < limit - 512
        )
        pressure = measurement if state.config.context_window_tokens and (limit <= 0 or measurement[0] >= limit) else None
        provider_context = (
            state.conversation.prepare_request(
                transcript,
                context_window_tokens=state.config.context_window_tokens,
                model_messages=model_messages,
                supplemental_messages=supplemental_messages,
            )
            if transcript is not None
            else state.conversation.independent_request_context(
                context_window_tokens=state.config.context_window_tokens,
            )
        )
        if pressure is not None:
            budget_limit = input_budget(state.config)
            if (
                budget_limit > 0
                and provider_context is not None
                and provider_context.conversation_state is not None
                and state.config.provider.supports_pre_request_compaction(state.config.model)
                is True
            ):
                # Keep the resumable state until its owner has compacted it. Inline
                # server compaction alone cannot make an oversized request safe.
                provider_context = replace(provider_context, compaction_input_budget=budget_limit)
                logger.info(
                    "Request requires provider pre-request compaction for {}: tokens={} budget={} via {}",
                    state.config.session_key or "default",
                    pressure[0],
                    budget_limit,
                    pressure[1],
                )
            else:
                prepared = await self.compaction.compact_history(
                    state,
                    state.compaction,
                    messages,
                    pressure,
                    tool_definitions=tool_definitions,
                )
                provider_context = state.conversation.independent_request_context(
                    context_window_tokens=state.config.context_window_tokens,
                )
        provider_context = replace(
            provider_context or ProviderCallContext(),
            events=state.events,
            input_tokens=state.input_tokens,
            output_reserve_percent=state.config.output_reserve_percent,
        )
        state.messages, state.tool_definitions = await self.preparation.run(
            request_snapshot,
            prepared,
            tool_definitions,
        )
        return prepared, provider_context
