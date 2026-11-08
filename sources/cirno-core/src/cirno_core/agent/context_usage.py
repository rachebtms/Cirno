"""Measure a saved request under its own scope without blocking the event loop."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.security.workspace_access import bind_workspace_scope, reset_workspace_scope

if TYPE_CHECKING:
    from cirno_core.memory.consolidation import Consolidator
    from cirno_core.security.workspace_access import WorkspaceScopeResolver
    from cirno_core.session.model import Session
    from cirno_core.utils.llm_runtime import LLMRuntime


async def measure_context_usage(
    session: Session,
    runtime: LLMRuntime,
    *,
    consolidator: Consolidator,
    workspace_scopes: WorkspaceScopeResolver,
) -> tuple[int, str]:
    channel, _, chat_id = session.key.partition(":")
    scope = workspace_scopes.for_turn(
        channel=channel,
        message_metadata={},
        session_metadata=session.metadata,
    )
    with request_context(
        RequestContext(
            channel=channel,
            chat_id=chat_id,
            session_key=session.key,
            session_generation=session.generation,
            runtime=runtime,
            workspace=scope.project_path,
            workspace_scope=scope,
            log_content=session.policy.log_content,
            persist_session=session.policy.persist,
        )
    ):
        token = bind_workspace_scope(scope)
        try:
            return await asyncio.to_thread(
                consolidator.estimate_session_prompt_tokens,
                session,
                runtime=runtime,
            )
        finally:
            reset_workspace_scope(token)
