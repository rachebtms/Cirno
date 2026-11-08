"""A replacement summary becomes authoritative only after its full request fits."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.governance import (
    ContextCompactionState,
    ContextGovernanceConfig,
    ContextGovernor,
    ContextWindowExceededError,
    ModelRequestState,
)
from cirno_core.bus.agent_events import ContextCompactionEvent, EventSink
from cirno_core.providers.conversation_state import ProviderConversationStateController
from cirno_core.session.summary import SessionSummaryCheckpoint
from cirno_usage.types import LLMUsage


@pytest.mark.parametrize("failure", ["over_budget", "counter_failed", "cancelled"])
async def test_rejected_compaction_preserves_the_previous_accepted_state(monkeypatch, failure):
    estimates = 0

    def measure(*args):
        nonlocal estimates
        estimates += 1
        if failure == "over_budget" or estimates == 1:
            return 10_000, "fixture"
        if estimates == 3:
            if failure == "cancelled":
                raise asyncio.CancelledError()
            raise RuntimeError("Token counter failed")
        return 100, "fixture"

    monkeypatch.setattr("cirno_core.agent.governance.budget.estimate_prompt_tokens_chain", measure)
    provider = MagicMock()
    raw = [
        {"role": "system", "content": "Stable instructions"},
        {"role": "user", "content": "Earlier research"},
    ]
    compaction = ContextCompactionState.from_messages(
        raw, AsyncMock(return_value="Uncommitted summary"), None
    )
    compaction.active_summary = "Previously accepted summary"
    compaction.checkpoint_reminded = True
    checkpoint = SessionSummaryCheckpoint(summary=compaction.active_summary, transcript_boundary=1)
    compaction.summary_checkpoint = checkpoint
    state = ModelRequestState(
        config=ContextGovernanceConfig(
            provider=provider,
            model="test",
            tools=MagicMock(),
            workspace=None,
            session_key="websocket:research",
            max_tool_result_chars=2048,
            context_window_tokens=2000,
            max_tokens=100,
        ),
        compaction=compaction,
        conversation=ProviderConversationStateController(
            provider=provider, model="test", messages=raw
        ),
        usage=LLMUsage.reported(input_tokens=1000, output_tokens=20),
    )
    events = []

    async def observe(event):
        events.append(event)

    state.events = EventSink(observe)
    original = deepcopy(raw)
    usage = state.usage
    exception = {
        "over_budget": ContextWindowExceededError,
        "counter_failed": RuntimeError,
        "cancelled": asyncio.CancelledError,
    }[failure]
    with pytest.raises(exception):
        await ContextGovernor().prepare_request(
            state,
            [*raw, {"role": "user", "content": "Oversized pending input"}],
            tool_definitions=[],
        )
    assert compaction.active_summary == "Previously accepted summary"
    assert compaction.checkpoint_reminded is True
    assert compaction.summary_checkpoint is checkpoint
    assert state.usage is usage
    assert compaction.accepted_messages == original
    assert raw == original
    assert [event.phase for event in events if isinstance(event, ContextCompactionEvent)] == [
        "started",
        "cancelled" if failure == "cancelled" else "failed",
    ]
    assert events[0].compaction_id == events[1].compaction_id
