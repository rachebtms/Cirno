"""One Dream batch lifecycle shared by manual, idle and scheduled runs."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

from cirno_core.memory.dream import DreamMemory
from cirno_core.memory.leases import run_with_dream_lease
from cirno_core.utils.cancellation import shield_and_drain

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.memory.store import MemoryStore


@dataclass(frozen=True)
class DreamRunResult:
    status: Literal["empty", "completed", "incomplete"]
    elapsed: float
    cursor: int | None = None
    changed: bool = False
    reason: str = ""
    commit: str | None = None


def commit_dream_changes(store: MemoryStore, subject: str) -> str | None:
    """Version actual durable changes, including partial edits from failed runs."""
    if not store.git.is_initialized():
        return None
    diff = store.dream.content_diff()
    if not diff:
        return None
    return store.git.auto_commit(DreamMemory.commit_message(subject, diff))


async def run_dream(
    agent: AgentLoop,
    *,
    commit_subject: str,
    prepare: Callable[[], Awaitable[None]] | None = None,
) -> DreamRunResult:
    """One batch owns the mutable prompt/tool scope until physical cleanup settles."""
    async with agent.context.memory.dream.run_lock:
        return await _run_batch(agent, commit_subject=commit_subject, prepare=prepare)


async def _run_batch(
    agent: AgentLoop,
    *,
    commit_subject: str,
    prepare: Callable[[], Awaitable[None]] | None,
) -> DreamRunResult:
    """Settle only confirmed input, release leases and propagate failed operations."""
    store = agent.context.memory
    started = time.monotonic()
    token = None
    completed = False
    failure = "Dream did not complete"
    preempted = False
    result = DreamRunResult(status="empty", elapsed=0)
    commit = None

    async def silent(*_args: Any, **_kwargs: Any) -> None:
        """Dream progress stays internal; its receipts provide durable status."""

    async def prepare_batch() -> tuple[str, int] | None:
        nonlocal token
        previous = store.dream.batch_token
        try:
            return await asyncio.to_thread(store.dream.build_prompt)
        finally:
            # A prompt read can fail after the repository has claimed a batch.
            # The run lock keeps another invocation from changing this ownership.
            if store.dream.batch_token != previous:
                token = store.dream.batch_token

    def settle_batch() -> dict[str, Any]:
        settlement = store.dream.finish_batch(token) or {}
        if settlement.get("retained", 0) == 0:
            store.journal.set_last_dream_cursor(cursor)
        return settlement

    def finalize() -> str | None:
        store.dream.finish_batch(
            token,
            error=None if completed else failure,
            preempted=preempted,
        )
        commit = commit_dream_changes(store, commit_subject)
        store.journal.compact_history()
        return commit

    try:
        batch = await shield_and_drain(prepare_batch())
        if batch is not None:
            prompt, cursor = batch
            token = store.dream.batch_token
            assert token is not None, "A prepared Dream batch must own a lease"
            if prepare is not None:
                await prepare()
            response = await run_with_dream_lease(
                agent.process_direct(
                    prompt,
                    session_key=DreamMemory.session_key(),
                    ephemeral=True,
                    tools=store.dream.build_tools(),
                    on_progress=silent,
                    runtime=agent.dream_runtime(),
                ),
                token,
                store.workspace,
            )
            diff = await asyncio.to_thread(store.dream.content_diff)
            completed = DreamMemory.run_completed(response)
            if completed:
                settlement = await shield_and_drain(asyncio.to_thread(settle_batch))
                token = None
                completed = settlement.get("retained", 0) == 0
                if not completed:
                    failure = f"{settlement['retained']} inputs remain unconfirmed or failed"
            else:
                failure = DreamMemory.incompletion_reason(response)
            result = DreamRunResult(
                status="completed" if completed else "incomplete",
                elapsed=time.monotonic() - started,
                cursor=cursor if completed else None,
                changed=bool(diff),
                reason="" if completed else failure,
            )
    except asyncio.CancelledError:
        preempted = True
        raise
    except Exception as error:
        failure = str(error)
        raise
    finally:
        commit = await shield_and_drain(asyncio.to_thread(finalize))
        await agent.sessions.state.prune_dream_sessions()
    return replace(result, commit=commit)
