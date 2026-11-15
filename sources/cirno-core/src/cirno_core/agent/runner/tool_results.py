"""Commit completed tool work before cancellation or output preparation can lose it."""

from __future__ import annotations

import asyncio
from typing import Any

from cirno_core.agent.governance.contracts import ModelRequestState
from cirno_core.agent.governance.messages import prepare_messages
from cirno_core.agent.governance.preparation import PromptPreparation
from cirno_core.agent.governance.results import apply_tool_result_budget
from cirno_core.agent.runner.contracts import AgentRunSpec
from cirno_core.agent.runner.history import emit_checkpoint
from cirno_core.providers.contracts import LLMResponse, ProviderConversationState
from cirno_core.providers.tool_calls import ToolCallRequest


class ToolResultCheckpoints:
    """Keep a partial batch's completed observations while its siblings run."""

    def __init__(self, spec: AgentRunSpec, state: ModelRequestState,
                 response: LLMResponse, assistant: dict[str, Any], iteration: int,
                 preparation: PromptPreparation) -> None:
        self.spec, self.state, self.response = spec, state, response
        self.assistant, self.iteration, self.preparation = assistant, iteration, preparation
        self.completed: dict[str, dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    async def record(self, call: ToolCallRequest, result: Any) -> None:
        if self.spec.checkpoint_callback is None:
            return
        async with self.lock:
            raw = {
                "role": "tool", "tool_call_id": call.id, "name": call.name, "content": result,
            }
            self.completed[call.id] = raw
            try:
                rows = await self.preparation.run(apply_tool_result_budget, self.state.config, [raw])
            except (Exception, asyncio.CancelledError):
                await self.publish()
                raise
            self.completed[call.id] = rows[0]
            await self.publish()

    async def publish(self) -> None:
        await emit_checkpoint(self.spec, {
            "phase": "tools_completed" if len(self.completed) == len(self.response.tool_calls) else "awaiting_tools",
            "iteration": self.iteration,
            "model": self.spec.runtime.model, "assistant_message": self.assistant,
            "completed_tool_results": [self.completed[item.id] for item in self.response.tool_calls
                                       if item.id in self.completed],
            "pending_tool_calls": [item.to_openai_tool_call() for item in self.response.tool_calls
                                   if item.id not in self.completed],
            "provider_state": None,
        })


async def commit_completed_tools(
    spec: AgentRunSpec,
    state: ModelRequestState,
    messages: list[dict[str, Any]],
    response: LLMResponse,
    assistant_message: dict[str, Any],
    results: list[Any],
    iteration: int,
    preparation: PromptPreparation,
) -> None:
    raw_results = [
        {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": result}
        for call, result in zip(response.tool_calls, results, strict=True)
    ]

    async def checkpoint(
        completed: list[dict[str, Any]], provider_state: ProviderConversationState | None
    ) -> None:
        messages.extend(completed)
        await emit_checkpoint(
            spec,
            {
                "phase": "tools_completed",
                "iteration": iteration,
                "model": spec.runtime.model,
                "assistant_message": assistant_message,
                "completed_tool_results": completed,
                "pending_tool_calls": [],
                "provider_state": provider_state,
            },
        )

    try:
        completed = await preparation.run(apply_tool_result_budget, state.config, raw_results)
        candidate = [*messages, *completed]
        model_messages = (
            await preparation.run(prepare_messages, state.config, candidate)
            if response.provider_state is not None
            else None
        )
        provider_state = await preparation.run(
            state.conversation.checkpoint,
            candidate,
            model_messages=model_messages,
        )
    except (Exception, asyncio.CancelledError):
        # Execution already succeeded. Preserve its exact results for recovery
        # and report the storage/preparation error instead of rerunning the tool.
        await checkpoint(raw_results, None)
        raise
    await checkpoint(completed, provider_state)
