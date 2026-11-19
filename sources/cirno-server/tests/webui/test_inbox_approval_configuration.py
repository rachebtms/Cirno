"""Inbox and approval operations use their server's selected configuration."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.approval.service import OperationApproval
from cirno_core.agent.tools.context import RequestContext
from cirno_core.agent.tools.instance_features import NodeTool
from cirno_core.config.home import set_instance_path
from cirno_core.config.loader import get_config_path, set_config_path
from cirno_core.credentials.service import Credentials
from cirno_core.notifications.inbox import NotificationInbox
from cirno_core.security.approval.store import ApprovalStore
from cirno_core.storage.instance import InstanceData
from cirno_server.webui.instance_api import instance_action


@pytest.mark.parametrize("action", ["inbox.list", "inbox.read"])
async def test_inbox_request_uses_its_explicit_server_state(tmp_path, action):
    first, second = tmp_path / "first", tmp_path / "second"
    set_instance_path(first)
    set_config_path(second / "config.json")
    original, unrelated = NotificationInbox(first / "state"), NotificationInbox(second / "state")
    for owner, text in ((original, "original"), (unrelated, "unrelated")):
        owner.record("fixture", "system", "fixture", body=text)
    result = await instance_action({"action": action, "values": {"ids": ["fixture"]}}, sessions=None, bus=None, config_path=first / "server.json")
    if action == "inbox.list":
        assert result["items"][0]["body"] == "original"
    else:
        assert original.list()["unread"]["system"] == 0
        assert unrelated.list()["unread"]["system"] == 1


def dependencies():
    header = SimpleNamespace(generation="fixture", messages=[], metadata={})

    async def mutate(_key, apply, **_kwargs):
        metadata = {}
        apply(metadata)
        return None, metadata

    sessions = SimpleNamespace(approval_settlement_lock=asyncio.Lock(), state=SimpleNamespace(
        read=AsyncMock(return_value=header), read_header=AsyncMock(return_value=header),
        mutate_metadata=mutate, queue_followup=AsyncMock(return_value="fixture"),
    ))
    bus = SimpleNamespace(publish=AsyncMock(), publish_inbound=AsyncMock())
    return sessions, bus


async def test_approval_review_reloads_its_own_settings_after_global_selection_changes(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    set_instance_path(first)
    set_config_path(first / "config.json")
    sessions, bus = dependencies()
    service = OperationApproval(sessions, bus)
    set_config_path(second / "config.json")
    observed = []

    def config(path=None):
        observed.append(path if path is not None else get_config_path())
        return SimpleNamespace(agents=SimpleNamespace(defaults=SimpleNamespace(approval=SimpleNamespace(enabled=False))))

    operation = {"tool": "fixture", "arguments": {}}
    monkeypatch.setattr("cirno_core.agent.approval.service.load_config", config)
    monkeypatch.setattr("cirno_core.agent.approval.service.operation_evidence", lambda *_args, **_kwargs: operation)
    request = RequestContext("websocket", "fixture", session_key="websocket:fixture", session_generation="fixture", turn_id="fixture", workspace=tmp_path)
    with pytest.raises(PermissionError, match="pending"):
        await service.authorize(SimpleNamespace(name="fixture"), {}, request, "Fixture boundary")
    assert observed == [first / "config.json"]
    assert len(service.inbox.list()["items"]) == 1
    assert not (second / "state").exists()


async def test_approval_decision_uses_the_request_config_state(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    set_instance_path(first)
    set_config_path(second / "config.json")
    store = ApprovalStore(first / "state" / "security" / "approvals.sqlite3")
    request = RequestContext("websocket", "fixture", session_key="websocket:fixture", session_generation="fixture", turn_id="fixture")
    item = store.record("fixture", request, {"tool": "fixture", "arguments": {}}, "pending", "Owner decision needed")
    sessions, bus = dependencies()
    result = await instance_action({"action": "approvals.decide", "values": {"id": item["id"], "approved": True}},
                                   sessions=sessions, bus=bus, config_path=first / "server.json")
    assert result == {"id": item["id"], "status": "approved"}
    assert store.get(item["id"])["status"] == "approved"
    assert NotificationInbox(first / "state").list()["items"][0]["status"] == "approved"


async def test_node_review_inspects_the_tool_connection_instead_of_the_global_instance(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    set_instance_path(first)
    set_config_path(first / "config.json")
    original = Credentials(InstanceData(first / "state"))
    row = original.save(label="Original", kind="ssh", node_enabled=True, agent_visible=True,
                        ssh={"host": "original.example", "username": "fixture", "auth_method": "password", "password": "source-secret"})
    unrelated = Credentials(InstanceData(second / "state"))
    clone = original.ssh(row["id"]).model_copy(update={"host": "unrelated.example"})
    unrelated.vault.save(create_id=row["id"], label="Unrelated", kind="ssh", value=clone.model_dump_json(), agent_visible=True)
    sessions, bus = dependencies()
    service = OperationApproval(sessions, bus)
    tool = NodeTool()
    set_config_path(second / "config.json")
    monkeypatch.setattr("cirno_core.agent.approval.service.load_config", lambda *_args: SimpleNamespace(
        agents=SimpleNamespace(defaults=SimpleNamespace(approval=SimpleNamespace(enabled=False))),
    ))
    request = RequestContext("websocket", "fixture", session_key="websocket:fixture", session_generation="fixture", turn_id="fixture", workspace=tmp_path)
    with pytest.raises(PermissionError, match="pending"):
        await service.authorize(tool, {"node_id": row["id"], "command": "uptime"}, request, "SSH boundary")
    notice = service.inbox.list()["items"][0]
    operation = service.store.get(notice["data"]["approval_id"])["operation"]
    assert json.loads(operation)["remote_target"]["host"] == "original.example"
    assert "source-secret" not in operation
