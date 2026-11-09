"""Execute an admitted private task through the common Agent runner."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial
from typing import TYPE_CHECKING, Any

from cirno_usage.context import current_llm_usage_source
from loguru import logger

from cirno_core.agent.hooks import create_file_edit_activity_hook
from cirno_core.agent.runner.contracts import AgentRunSpec
from cirno_core.agent.runner.engine import AgentRunner
from cirno_core.agent.session_activity import SessionActivity
from cirno_core.agent.subagents.contracts import SubagentLimits, SubagentOutcome
from cirno_core.agent.subagents.progress import SubagentProgress
from cirno_core.agent.subagents.status import SubagentStatus
from cirno_core.agent.subagents.task import SubagentTask
from cirno_core.agent.subagents.tools import SubagentTools
from cirno_core.agent.tools.context import (
    RequestContext,
    bind_request_context,
    reset_request_context,
)
from cirno_core.agent.turn_hooks import AgentTurnHookSpec, build_agent_turn_hook
from cirno_core.bus.agent_events import AgentEvent, EventSink
from cirno_core.security.workspace_access import bind_workspace_scope, reset_workspace_scope

if TYPE_CHECKING:
    from cirno_core.memory.consolidation import Consolidator


class SubagentExecution:
    def __init__(
        self,
        tools: SubagentTools,
        limits: SubagentLimits,
        consolidator: Consolidator,
        *,
        save_transcript: Callable[[SubagentTask], Awaitable[None]],
        save_status: Callable[[SubagentStatus], Awaitable[None]],
        drain_inbox: Callable[[SubagentTask], Awaitable[list[dict[str, str]]]],
    ):
        self.tools, self.limits, self.consolidator = tools, limits, consolidator
        self.save_transcript, self.save_status, self.drain_inbox = (
            save_transcript,
            save_status,
            drain_inbox,
        )
        self.runner = AgentRunner()

    async def run(self, record: SubagentTask) -> SubagentOutcome:
        """Execute the admitted task with task-owned shell resources."""
        status, origin, runtime = record.status, record.origin, record.runtime
        task_id, label = status.task_id, status.label
        origin_message_id, workspace_scope = record.origin_message_id, record.workspace_scope
        logger.info(
            "Subagent [{}] starting task: {}",
            task_id,
            label if record.session.policy.log_content else "[content hidden]",
        )

        async def _on_checkpoint(payload: dict[str, Any]) -> None:
            record.raise_if_stopping()
            phase = payload.get("phase", status.phase)
            iteration = payload.get("iteration", status.iteration)
            if (phase, iteration) != (status.phase, status.iteration):
                status.phase, status.iteration = phase, iteration
                await self.save_status(status)

        root = workspace_scope.project_path if workspace_scope is not None else self.tools.workspace
        cfg = None
        if workspace_scope is not None:
            cfg = self.tools.configuration()
            cfg.restrict_to_workspace = workspace_scope.restrict_to_workspace
        # Construct from the agent workspace; the bound scope below supplies the project cwd.
        tools = self.tools.build(tools_config=cfg, exec_manager=record.exec_manager)
        system_prompt = await self.runner.prepare_prompt(self.tools.prompt, workspace=root)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *record.session.get_history(),
        ]
        activity = SessionActivity()

        async def save_observation(status: SubagentStatus) -> None:
            record.session.messages = activity.transcript()
            await self.save_transcript(record)
            await self.save_status(status)

        async def publish_activity(event: AgentEvent) -> None:
            if activity.remember(event):
                await save_observation(status)

        events = EventSink(publish_activity)
        hook = build_agent_turn_hook(
            AgentTurnHookSpec(
                events=events,
                streaming=True,
                channel=origin["channel"],
                chat_id=origin["chat_id"],
                message_id=origin_message_id,
                session_key=record.session.key,
                workspace=root,
                registered_hook_factories=[create_file_edit_activity_hook],
                turn_hooks=[
                    activity,
                    SubagentProgress(
                        status,
                        check_active=record.raise_if_stopping,
                        max_result_chars=self.limits.max_tool_result_chars,
                        on_status=save_observation,
                    ),
                ],
                ephemeral=not record.session.policy.persist,
                run_extra_hooks_for_ephemeral=True,
                log_content=record.session.policy.log_content,
            )
        )

        request_token = bind_request_context(
            RequestContext(
                channel=origin["channel"],
                chat_id=origin["chat_id"],
                message_id=origin_message_id,
                session_key=record.session.key,
                runtime=runtime,
                log_content=record.session.policy.log_content,
                persist_session=record.session.policy.persist,
            )
        )
        token = bind_workspace_scope(workspace_scope) if workspace_scope is not None else None
        try:
            tool_definitions = tools.get_definitions()
            consolidate_history = partial(
                self.consolidator.summarize_transcript,
                runtime=runtime,
                session_key=record.session.key,
                tools=tool_definitions,
                persist=False,
            )
            consolidate_provider_compaction = partial(
                self.consolidator.summarize_provider_compaction,
                runtime=runtime,
                session_key=record.session.key,
                tools=tool_definitions,
                persist=False,
            )
            result = await self.runner.run(
                AgentRunSpec(
                    initial_messages=messages,
                    tools=tools,
                    runtime=runtime,
                    max_iterations=self.limits.max_iterations,
                    max_tool_result_chars=self.limits.max_tool_result_chars,
                    hook=hook,
                    max_iterations_message="Task stopped at its iteration limit before producing a final response.",
                    finalize_on_max_iterations=False,
                    error_message=None,
                    checkpoint_callback=_on_checkpoint,
                    injection_callback=partial(self.drain_inbox, record),
                    session_key=record.session.key,
                    workspace=root if record.session.policy.persist else None,
                    llm_usage_source=origin.get(
                        "llm_usage_source",
                        current_llm_usage_source(),
                    ),
                    consolidate_history=consolidate_history,
                    consolidate_provider_compaction=consolidate_provider_compaction,
                    events=events,
                )
            )
        finally:
            if token is not None:
                reset_workspace_scope(token)
            reset_request_context(request_token)
        status.usage = result.usage
        if result.messages:
            record.session.messages = activity.transcript(result.messages)
        record.session.provider_state = result.provider_state
        checkpoint = result.summary_checkpoint
        if checkpoint is not None:
            boundary = checkpoint.transcript_boundary
            if 0 <= boundary <= len(result.messages):
                insert_at = sum(
                    message.get("role") != "system" for message in result.messages[:boundary]
                )
                record.session.commit_summary_checkpoint(checkpoint.summary, insert_at=insert_at)
        if result.stop_reason in {"error", "empty_final_response"}:
            final_result = result.error or "Error: subagent execution failed."
            return SubagentOutcome("error", final_result, result.stop_reason, result.error)
        if result.stop_reason == "max_iterations":
            return SubagentOutcome(
                "incomplete", result.final_content or "Iteration limit reached.", result.stop_reason
            )
        final_result = result.final_content or "Task completed but no final response was generated."
        return SubagentOutcome("done", final_result, result.stop_reason, result.error)
