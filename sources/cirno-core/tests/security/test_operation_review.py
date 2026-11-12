"""Review never executes a probe, imports memory, or widens later calls."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cirno_core.agent.tools.context import RequestContext
from cirno_core.agent.tools.filesystem import WriteFileTool
from cirno_core.bus.events import INBOUND_META_TURN_ID
from cirno_core.bus.queue import MessageBus
from cirno_core.notifications.inbox import NotificationInbox
from cirno_core.agent.approval.service import OperationApproval, operation_access
from cirno_core.security.approval.store import ApprovalStore
from cirno_core.security.workspace_access import bind_workspace_scope, build_workspace_scope, current_workspace_scope, reset_workspace_scope
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.contracts import REQUEST_ORIGIN_METADATA_KEY


@pytest.fixture
async def review(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sessions = SessionManager(workspace)
    key = "websocket:review"
    target = tmp_path / "result.txt"
    session = await sessions.state.import_messages(key, [{"role": "user", "content": f"Write hello to {target}", INBOUND_META_TURN_ID: "human"}])
    response = AsyncMock(return_value=SimpleNamespace(content='{"decision":"approve","reason":"The owner requested this exact file."}'))
    runtime = SimpleNamespace(provider=SimpleNamespace(chat_with_retry=response), model="review-model")
    scope = build_workspace_scope(workspace, "review", source_channel="websocket")
    bus = MessageBus()
    service = OperationApproval(sessions, bus, store=ApprovalStore(tmp_path / "approvals.sqlite3"), inbox=NotificationInbox(tmp_path))
    request = RequestContext(channel="websocket", chat_id="review", session_key=key, session_generation=session.generation,
                             turn_id="human", workspace=workspace, workspace_scope=scope, runtime=runtime, operation_approval=service)
    token = bind_workspace_scope(scope)
    yield service, request, response, target, sessions, bus
    reset_workspace_scope(token)
    await sessions.state.aclose()


async def test_exact_call_review_has_no_memory_and_restores_access(review):
    service, request, response, target, sessions, bus = review
    tool = WriteFileTool(workspace=request.workspace, allowed_dir=request.workspace)
    params = {"path": str(target), "content": "hello"}
    assert tool.approval_reason(params)
    assert not target.exists()
    async with operation_access(tool, params, request):
        assert current_workspace_scope().access_mode == "full"
        await tool.execute(**params)
    assert target.read_text() == "hello"
    assert current_workspace_scope().access_mode == "review"
    call = response.call_args.kwargs
    assert len(call["messages"]) == 2 and call["tools"] == []
    assert "SOUL" not in str(call["messages"]) and "MEMORY.md" not in str(call["messages"])
    assert call["messages"][1]["content"].count("Write hello to") == 1
    assert service.inbox.list()["items"][0]["status"] == "approved"


async def test_uncertain_waits_for_owner_and_grant_is_one_use(review):
    service, request, response, target, sessions, bus = review
    response.return_value.content = '{"decision":"human","reason":"Confirm the outside destination"}'
    tool = WriteFileTool(workspace=request.workspace, allowed_dir=request.workspace)
    params = {"path": str(target), "content": "hello"}
    await sessions.state.update_metadata(request.session_key, {"goal_state": {"objective": "Write the file", "status": "active", "continuation_count": 2}})
    with pytest.raises(PermissionError, match="pending"):
        async with operation_access(tool, params, request):
            pytest.fail("Pending operation executed")
    assert not target.exists()
    item = service.inbox.list()["items"][0]
    goal = (await sessions.state.read_header(request.session_key)).metadata["goal_state"]
    assert goal["status"] == "waiting" and "wake_at" not in goal
    with pytest.raises(PermissionError, match="pending"):
        async with operation_access(tool, params, request):
            pass
    assert response.call_count == 1
    identifier = item["data"]["approval_id"]
    await service.decide(identifier, True)
    inbound = await bus.consume_inbound()
    assert inbound.sender_id == "system:approval" and inbound.session_generation == request.session_generation
    assert inbound.metadata[REQUEST_ORIGIN_METADATA_KEY]["turn_id"] == "human"
    goal = (await sessions.state.read_header(request.session_key)).metadata["goal_state"]
    assert goal["status"] == "active" and goal["continuation_count"] == 2
    async with operation_access(tool, params, request):
        await tool.execute(**params)
    assert response.call_count == 1
    assert service.store.get(identifier)["status"] == "used"
    with pytest.raises(ValueError, match="already"):
        await service.decide(identifier, True)
    with pytest.raises(PermissionError, match="pending"):
        async with operation_access(tool, {**params, "content": "different operation"}, request):
            pass
    assert response.call_count == 2


async def test_replaced_session_cannot_consume_owner_grant(review):
    service, request, response, target, sessions, bus = review
    response.return_value.content = '{"decision":"human","reason":"Need confirmation"}'
    tool = WriteFileTool(workspace=request.workspace, allowed_dir=request.workspace)
    with pytest.raises(PermissionError):
        async with operation_access(tool, {"path": str(target), "content": "hello"}, request):
            pass
    item = service.inbox.list()["items"][0]
    await sessions.state.delete(request.session_key)
    await sessions.state.get(request.session_key)
    with pytest.raises(ValueError, match="replaced"):
        await service.decide(item["data"]["approval_id"], True)
    with pytest.raises(PermissionError, match="replaced"):
        async with operation_access(tool, {"path": str(target), "content": "hello"}, request):
            pass
    assert not target.exists()


async def test_invalid_review_and_denial_never_execute(review):
    service, request, response, target, sessions, bus = review
    response.side_effect = RuntimeError("provider unavailable")
    tool = WriteFileTool(workspace=request.workspace, allowed_dir=request.workspace)
    with pytest.raises(PermissionError, match="provider unavailable"):
        async with operation_access(tool, {"path": str(target), "content": "hello"}, request):
            pass
    assert not target.exists()
    response.side_effect = None
    response.return_value.content = '{"decision":"deny","reason":"Unrelated destruction"}'
    with pytest.raises(PermissionError, match="denied"):
        async with operation_access(tool, {"path": str(target), "content": "delete"}, request):
            pass
    assert not target.exists()
    # Default has no review capability or grant and remains restricted.
    restricted = replace(request, workspace_scope=build_workspace_scope(request.workspace, "restricted"))
    token = bind_workspace_scope(restricted.workspace_scope)
    try:
        async with operation_access(tool, {"path": str(target), "content": "hello"}, restricted):
            result = await tool.execute(path=str(target), content="hello")
        assert "outside" in result
    finally:
        reset_workspace_scope(token)


async def test_review_is_enforced_at_shared_tool_boundary(review):
    from cirno_core.agent.hook import AgentHook, AgentHookContext
    from cirno_core.agent.tools.context import request_context
    from cirno_core.agent.tools.execution import execute_tool_calls
    from cirno_core.agent.tools.registry import ToolRegistry
    from cirno_core.providers.tool_calls import ToolCallRequest

    service, request, response, target, sessions, bus = review
    response.return_value.content = '{"decision":"deny","reason":"Do not write that destination"}'
    tools = ToolRegistry()
    tools.register(WriteFileTool(workspace=request.workspace, allowed_dir=request.workspace))
    with request_context(request):
        result, events = await execute_tool_calls(tools, [ToolCallRequest(id="attempt", name="write_file", arguments={"path": str(target), "content": "hello"})],
                                                  concurrent=False, external_lookup_counts={}, workspace_violation_counts={}, hook=AgentHook(), context=AgentHookContext(iteration=1, messages=[]))
    assert events[0]["status"] == "error" and "denied" in str(result[0])
    assert not target.exists() and current_workspace_scope().access_mode == "review"


async def test_script_content_changes_require_fresh_review(review):
    from cirno_core.agent.tools.shell import ExecTool
    from cirno_core.agent.approval.reviewer import operation_evidence

    service, request, response, target, sessions, bus = review
    script = request.workspace / "run.py"
    script.write_text("print('safe original')")
    response.return_value.content = '{"decision":"human","reason":"Confirm script execution"}'
    tool = ExecTool(working_dir=str(request.workspace), restrict_to_workspace=True)
    params = {"command": f"python {script}", "working_dir": str(target.parent)}
    with pytest.raises(PermissionError, match="pending"):
        async with operation_access(tool, params, request):
            pass
    identifier = service.inbox.list()["items"][0]["data"]["approval_id"]
    await service.decide(identifier, True)
    script.write_text("print('changed operation')")
    with pytest.raises(PermissionError, match="pending"):
        async with operation_access(tool, params, request):
            pass
    assert response.call_count == 2
    assert service.store.get(identifier)["status"] == "approved"
    evidence = operation_evidence("exec", params, request.workspace)
    assert evidence["scripts"][0]["content"] == "print('changed operation')"


async def test_owner_decision_is_recovered_if_delivery_is_interrupted(review, monkeypatch):
    from cirno_core.session.recovery.pending import pending_followups
    service, request, response, target, sessions, bus = review
    response.return_value.content = '{"decision":"human","reason":"Owner decision required"}'
    tool = WriteFileTool(workspace=request.workspace, allowed_dir=request.workspace)
    params = {"path": str(target), "content": "hello"}
    with pytest.raises(PermissionError):
        async with operation_access(tool, params, request):
            pass
    identifier = service.inbox.list()["items"][0]["data"]["approval_id"]
    record = service.inbox.record
    monkeypatch.setattr(service.inbox, "record", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("notification disk error")))
    with pytest.raises(OSError, match="disk error"):
        await service.decide(identifier, True)
    assert service.store.pending_wakes()[0]["id"] == identifier
    monkeypatch.setattr(service.inbox, "record", record)
    await service.recover()
    assert not service.store.pending_wakes()
    pending = pending_followups(await sessions.state.get(request.session_key))
    assert len(pending) == 1 and pending[0].sender_id == "system:approval"
    # A second startup does not enqueue another decision.
    await service.recover()
    assert len(pending_followups(await sessions.state.get(request.session_key))) == 1


async def test_approval_expiry_starts_at_owner_decision(review):
    service, request, response, target, sessions, bus = review
    response.return_value.content = '{"decision":"human","reason":"Owner decision required"}'
    tool = WriteFileTool(workspace=request.workspace, allowed_dir=request.workspace)
    params = {"path": str(target), "content": "hello"}
    with pytest.raises(PermissionError):
        async with operation_access(tool, params, request):
            pass
    identifier = service.inbox.list()["items"][0]["data"]["approval_id"]
    with service.store.connect() as db:
        db.execute("UPDATE approvals SET created_at=created_at-7200 WHERE id=?", (identifier,))
    await service.decide(identifier, True)
    async with operation_access(tool, params, request):
        assert current_workspace_scope().access_mode == "full"


async def test_disabled_ai_review_queues_owner_approval_without_model_call(review, monkeypatch):
    from cirno_core.config.schema import Config
    config = Config()
    config.agents.defaults.approval.enabled = False
    monkeypatch.setattr("cirno_core.agent.approval.service.load_config", lambda: config)
    service, request, response, target, *_ = review
    tool = WriteFileTool(workspace=request.workspace, allowed_dir=request.workspace)
    with pytest.raises(PermissionError, match="pending"):
        async with operation_access(tool, {"path": str(target), "content": "hello"}, request):
            pytest.fail("Owner approval must precede execution")
    response.assert_not_called()
    assert not target.exists()
    assert service.inbox.list()["items"][0]["status"] == "pending"


async def test_independent_review_uses_selected_preset_and_timeout(review, monkeypatch):
    from cirno_core.config.schema import Config
    config = Config()
    config.agents.defaults.approval.model_override = "review-only"
    config.agents.defaults.approval.timeout_seconds = 73
    monkeypatch.setattr("cirno_core.agent.approval.service.load_config", lambda: config)
    service, request, response, target, *_ = review
    selected = object()
    service.model_resolver = SimpleNamespace(resolve_preset=lambda name: selected if name == "review-only" else None)
    evaluate = AsyncMock(return_value=("approve", "Exact requested operation"))
    monkeypatch.setattr("cirno_core.agent.approval.service.review_operation", evaluate)
    tool = WriteFileTool(workspace=request.workspace, allowed_dir=request.workspace)
    async with operation_access(tool, {"path": str(target), "content": "hello"}, request):
        assert current_workspace_scope().access_mode == "full"
    assert evaluate.call_args.args == (selected,)
    assert evaluate.call_args.kwargs["timeout_seconds"] == 73
    response.assert_not_called()


@pytest.mark.parametrize('mode', ['restricted', 'review', 'full'])
async def test_nodes_execute_obeys_access_and_review(review, monkeypatch, mode):
    import json
    from cirno_core.agent.tools.instance_features import NodeTool
    from cirno_core.nodes.service import Nodes
    from cirno_core.nodes.commands import CommandResult
    from cirno_core.agent.tools.context import request_context
    service, request, response, target, sessions, bus = review
    credential = Nodes().credentials.save(label='Research', kind='ssh', ssh={'host': 'lab.example', 'username': 'worker'}, node_enabled=True, agent_visible=True)
    node = Nodes().node(credential['id']).model_dump()
    execute = AsyncMock(return_value=CommandResult('remote result', '', 0))
    monkeypatch.setattr(Nodes, 'execute_command', execute)
    scope = build_workspace_scope(request.workspace, mode, source_channel='websocket')
    request = replace(request, workspace_scope=scope)
    params = {'action': 'execute', 'node_id': node['id'], 'command': 'printf hello'}
    token = bind_workspace_scope(scope)
    try:
        with request_context(request):
            async with operation_access(NodeTool(), params, request):
                result = await NodeTool().execute(**params)
        if mode == 'restricted':
            assert result.is_error
            execute.assert_not_awaited()
        else:
            execute.assert_awaited_once_with(node['id'], 'printf hello')
            assert json.loads(result) == {"stdout": "remote result", "stderr": "", "exit_code": 0}
        assert response.await_count == (1 if mode == 'review' else 0)
        if mode == 'review':
            evidence = json.loads(response.call_args.kwargs['messages'][1]['content'])['operation']
            assert evidence['remote_target']['host'] == 'lab.example'
            assert 'password' not in evidence['remote_target']
    finally:
        reset_workspace_scope(token)


async def test_remote_script_requires_human_not_a_local_lookalike(review, monkeypatch):
    from cirno_core.agent.tools.instance_features import NodeTool
    from cirno_core.nodes.service import Nodes
    service, request, response, target, sessions, bus = review
    credential = Nodes().credentials.save(label='Research', kind='ssh', ssh={'host': 'lab.example', 'username': 'worker'}, node_enabled=True, agent_visible=True)
    node = Nodes().node(credential['id']).model_dump()
    (request.workspace / 'task.py').write_text('print("safe locally")')
    params = {'action': 'execute', 'node_id': node['id'], 'command': 'python task.py'}
    with pytest.raises(PermissionError, match='pending'):
        async with operation_access(NodeTool(), params, request):
            pytest.fail('No remote effects before approval')
    response.assert_not_awaited()


@pytest.mark.parametrize('kind', ['text', 'ssh'])
async def test_credential_review_records_and_inbox_never_persist_secret_arguments(review, kind):
    import json
    from cirno_core.agent.tools.credential import CredentialTool
    service, request, response, target, sessions, bus = review
    secret = 'PRIVATE_REVIEW_VALUE_42'
    params = {'action': 'store', 'id': 'credential-to-update', 'label': 'Research login', 'kind': kind}
    params.update({'ssh': {'host': 'lab.example', 'username': 'worker', 'password': secret}} if kind == 'ssh' else {'value': secret})
    await service.authorize(CredentialTool(), params, request, 'Replace an encrypted credential')
    notice = service.inbox.list()['items'][0]
    persisted = service.store.get(notice['data']['approval_id'])
    assert secret not in json.dumps(response.call_args.kwargs)
    assert secret not in persisted['operation']
    assert secret not in json.dumps(notice)


def test_credential_review_digest_binds_redacted_values(tmp_path):
    from cirno_core.agent.approval.reviewer import operation_evidence
    first = operation_evidence('credential', {'action': 'store', 'id': 'record', 'value': 'first-secret'}, tmp_path)
    second = operation_evidence('credential', {'action': 'store', 'id': 'record', 'value': 'second-secret'}, tmp_path)
    assert 'first-secret' not in str(first)
    assert first['arguments'] == second['arguments']
    assert first != second
