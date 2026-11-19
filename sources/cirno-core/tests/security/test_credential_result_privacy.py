"""Explicit credential reads reach the current model, not durable activity/history."""

import json
from copy import deepcopy

from cirno_core.agent.loop import AgentLoop
from cirno_core.bus.queue import MessageBus
from cirno_core.credentials.service import Credentials
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_core.storage.instance import InstanceData


class CredentialReader(LLMProvider):
    def __init__(self, identifier):
        super().__init__(provider_name="fixture")
        self.identifier = identifier
        self.requests = []

    def get_default_model(self):
        return "fixture"

    async def chat(self, messages, tools=None, **kwargs):
        self.requests.append(deepcopy(messages))
        if len(self.requests) == 1:
            return LLMResponse(content=None, tool_calls=[ToolCallRequest(
                "read-secret", "credentials__read", {"id": self.identifier},
            )])
        return LLMResponse(content="Credential read for the authorized task")


async def test_credential_read_is_transient_in_model_context(tmp_path, monkeypatch):
    secret = "fixture-secret-never-save-to-history"
    owner = Credentials(InstanceData(tmp_path / "state"))
    record = owner.save(label="Task credential", value=secret, agent_visible=True)
    monkeypatch.setattr("cirno_core.agent.tools.credential.Credentials", lambda data=None, **kwargs: Credentials(owner.data, **kwargs))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = CredentialReader(record["id"])
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=workspace, model="fixture", max_iterations=3)
    events = []

    async def progress(content, **kwargs):
        events.append({"content": content, **kwargs})

    try:
        await loop.process_direct("Use the saved task credential", session_key="cli:credential-reader", on_progress=progress)
        assert secret in json.dumps(provider.requests[-1]), "Explicit reads must still reach the executing model"
        session = await loop.sessions.state.read("cli:credential-reader")
        assert secret not in json.dumps(session.messages), "Credential value was persisted in plain conversation history"
        assert secret not in json.dumps(events), "Credential value was exposed in tool activity"
    finally:
        await loop.aclose()


async def test_inflight_credential_checkpoint_hides_secret(tmp_path, monkeypatch):
    import asyncio

    secret = "fixture-secret-inflight"
    owner = Credentials(InstanceData(tmp_path / "state"))
    record = owner.save(label="Task credential", value=secret, agent_visible=True)
    monkeypatch.setattr("cirno_core.agent.tools.credential.Credentials", lambda data=None, **kwargs: Credentials(owner.data, **kwargs))
    provider = CredentialReader(record["id"])
    original_chat = provider.chat
    received = asyncio.Event()
    wait = asyncio.Event()

    async def chat(*args, **kwargs):
        if provider.requests:
            assert secret in json.dumps(args[0] if args else kwargs["messages"])
            received.set()
            await wait.wait()
        return await original_chat(*args, **kwargs)

    provider.chat = chat
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=workspace, model="fixture", max_iterations=3)
    running = asyncio.create_task(loop.process_direct("Use the saved credential", session_key="cli:inflight"))
    try:
        await asyncio.wait_for(received.wait(), timeout=2)
        session = await loop.sessions.state.read("cli:inflight")
        assert secret not in json.dumps(session.messages)
        assert secret not in json.dumps(session.metadata)
        for path in workspace.rglob("*"):
            if path.is_file():
                assert secret.encode() not in path.read_bytes(), path
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        await loop.aclose()


def test_oversized_credential_does_not_create_plaintext_spill(tmp_path):
    from cirno_core.agent.governance.contracts import ContextGovernanceConfig
    from cirno_core.agent.governance.results import normalize_tool_result
    from cirno_core.agent.tools.base import ToolResult
    from cirno_core.agent.tools.registry import ToolRegistry

    config = ContextGovernanceConfig(provider=CredentialReader("id"), model="fixture", tools=ToolRegistry(),
                                    workspace=tmp_path, session_key="cli:privacy", max_tool_result_chars=20)
    secret = ToolResult("secret-value-" * 50, sensitive=True)
    result = normalize_tool_result(config, "read", "credentials__read", secret)
    assert result.is_error
    assert "increase that limit" in result
    assert not list(tmp_path.rglob("*"))
    small = ToolResult("small", sensitive=True)
    assert normalize_tool_result(config, "read", "credentials__read", small) is small


def test_private_provider_record_redacts_only_durable_copy():
    from cirno_core.providers.contracts import ProviderConversationState
    from cirno_vault.redaction import CREDENTIAL_RESULT_HIDDEN

    calls = [{"type": "function_call", "name": "credentials__read", "call_id": "read", "arguments": '{"id":"id"}'},
             {"type": "function_call_output", "call_id": "read", "output": "fixture-secret"}]
    pending = [{"role": "tool", "name": "credentials__read", "tool_call_id": "other", "content": "fixture-secret"}]
    state = ProviderConversationState("responses", "fixture", "fixture", 1,
                                      payload={"items": calls, "opaque": "keep"}, pending_messages=pending)
    record = state.to_private_record()
    assert "fixture-secret" not in json.dumps(record)
    assert record["payload"]["items"][-1]["output"] == CREDENTIAL_RESULT_HIDDEN
    assert record["payload"]["opaque"] == "keep"
    assert state.payload["items"][-1]["output"] == "fixture-secret"
    assert state.pending_messages[-1]["content"] == "fixture-secret"


async def test_consolidation_archives_hidden_results_and_preserves_live_prefix(tmp_path):
    from unittest.mock import AsyncMock, MagicMock

    from cirno_core.memory.archiver import MemoryArchiver
    from cirno_core.memory.store import MemoryStore
    from cirno_core.providers.generation import GenerationSettings
    from cirno_core.utils.llm_runtime import LLMRuntime

    checkpoint = "## Task\nUse saved credential.\n## State\nCredential was read.\n## Next\nContinue.\n## Retained facts\n(none)"
    provider = MagicMock(spec=LLMProvider)
    provider.chat_stream_with_retry = AsyncMock(return_value=LLMResponse(content=checkpoint))
    runtime = LLMRuntime(provider, "fixture", GenerationSettings(max_tokens=8192), 512000)
    archiver = MemoryArchiver(MemoryStore(tmp_path), lambda **kw: kw["history"], lambda _: [])
    history = [{"role": "system", "content": "Stable prefix"},
               {"role": "assistant", "tool_calls": [{"id": "read", "function": {
                   "name": "credentials__read", "arguments": '{"id":"saved-id"}'}}]},
               {"role": "tool", "name": "credentials__read", "tool_call_id": "read", "content": "fixture-secret-to-archive"}]
    await archiver.archive(history[1:], runtime=runtime, session_key="worker:privacy", history=history, request_tools=[])
    assert "fixture-secret-to-archive" not in str(provider.chat_stream_with_retry.call_args)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert b"fixture-secret-to-archive" not in path.read_bytes(), path
    assert history[-1]["content"] == "fixture-secret-to-archive"
    assert history[0]["content"] == "Stable prefix"


def test_native_pending_result_can_resolve_call_name_from_prior_items():
    from cirno_core.providers.contracts import ProviderConversationState

    state = ProviderConversationState("responses", "fixture", "fixture", 1,
        payload={"items": [{"type": "function_call", "call_id": "read", "name": "credentials__read", "arguments": '{"id":"saved"}'}]},
        pending_messages=[{"role": "tool", "tool_call_id": "read", "content": "fixture-secret-split-state"}])
    assert "fixture-secret-split-state" not in json.dumps(state.to_private_record())
    assert state.pending_messages[-1]["content"] == "fixture-secret-split-state"
