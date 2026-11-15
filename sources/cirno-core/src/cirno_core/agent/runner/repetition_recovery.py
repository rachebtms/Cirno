"""Serial correction and durable boundaries after an output interruption."""

from typing import Any

from cirno_core.agent.hook import AgentHook, AgentHookContext
from cirno_core.agent.runner.contracts import AgentRunSpec
from cirno_core.agent.runner.history import checkpoint_reply
from cirno_core.agent.runner.repetition import REPETITION_PAUSED_NOTICE, OutputRepetitionGuard
from cirno_core.bus.outbound_events import ProgressEvent
from cirno_core.providers.contracts import LLMResponse, ProviderConversationState
from cirno_core.utils.model_messages import build_assistant_message


async def recover_repetition(
    spec: AgentRunSpec, messages: list[dict[str, Any]], response: LLMResponse,
    hook: AgentHook, context: AgentHookContext,
    provider_state: ProviderConversationState | None,
) -> tuple[bool, str]:
    guard = OutputRepetitionGuard(spec.output_repetition, messages)
    exhausted = (
        guard.interventions >= spec.output_repetition.max_interventions
        or context.iteration + 1 >= spec.max_iterations
    )
    notice = (
        REPETITION_PAUSED_NOTICE if exhausted
        else "Repeated output interrupted; sending guidance before continuing."
    )
    await spec.events.emit(ProgressEvent(content=notice, tool_hint=True))
    if hook.wants_streaming():
        await hook.on_stream_end(context, resuming=not exhausted)
    # No tool in this response batch ran. Keep already delivered prose, then
    # append guidance after the stable history; never replace its prefix.
    if response.content:
        messages.append(build_assistant_message(response.content))
    interrupted = build_assistant_message(notice)
    if not exhausted:
        interrupted["_hidden_history"] = {"kind": "repetition_interruption"}
    messages.append(interrupted)
    if not exhausted:
        messages.append(guard.guidance_message())
    await checkpoint_reply(spec, interrupted, context.iteration, provider_state, final=exhausted)
    context.stop_reason = "repetition_limit" if exhausted else "repetition"
    context.final_content = notice if exhausted else None
    await hook.after_iteration(context)
    return exhausted, notice
