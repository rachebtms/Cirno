"""Credential reads/mutations keep their owner and settle accepted local work."""

import asyncio
import json
import threading
from types import SimpleNamespace

import pytest
from cirno_core.agent.tools.context import ToolContext
from cirno_core.agent.tools.credential import CredentialTool
from cirno_core.config.home import set_instance_path
from cirno_core.config.loader import set_config_path
from cirno_core.config.tools import ToolsConfig
from cirno_core.credentials.service import Credentials
from cirno_core.storage.instance import InstanceData
from cirno_server.webui.workbench_api import WorkbenchAPI


def select(root):
    set_instance_path(root)
    set_config_path(root / "config.json")


@pytest.mark.parametrize("entry", ["tool", "factory", "workbench"])
async def test_credentials_retain_their_original_owner_after_global_selection_changes(tmp_path, monkeypatch, entry):
    first, second = tmp_path / "first", tmp_path / "second"
    select(first)
    row = Credentials(InstanceData(first / "state")).save(label="Fixture", value="owned-fixture", agent_visible=True)
    monkeypatch.setattr("cirno_server.webui.workbench_api.Terminals", lambda *, state_dir=None: SimpleNamespace())
    ctx = ToolContext(config=ToolsConfig(), workspace=str(tmp_path))
    owner = WorkbenchAPI(None, None) if entry == "workbench" else CredentialTool()
    select(second)
    if entry == "factory":
        owner = CredentialTool.create(ctx)
    if entry == "workbench":
        result = await owner.action({"action": "credentials.reveal", "values": {"id": row["id"]}})
    else:
        response = await owner.execute("read", id=row["id"])
        assert not response.is_error
        assert response.sensitive
        result = json.loads(response)
    assert result == {"value": "owned-fixture"}
    assert not (second / "state" / "credentials").exists()


@pytest.mark.parametrize("entry", ["tool", "workbench"])
@pytest.mark.parametrize("stage", ["initialize", "list", "reveal", "save", "delete"])
@pytest.mark.parametrize("fails", [False, True])
async def test_cancelling_credentials_waits_for_accepted_initialization_and_storage(tmp_path, monkeypatch, entry, stage, fails):
    select(tmp_path / "instance")
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    completed = threading.Event()
    marker = tmp_path / "credential-write"

    def write():
        loop.call_soon_threadsafe(entered.set)
        try:
            assert release.wait(2), "Fixture did not release accepted credential work"
            marker.write_text("settled", encoding="utf-8")
            if fails:
                raise ValueError("Fixture late credential write failure")
        finally:
            completed.set()

    def operation(kind):
        def perform(*_args, **_kwargs):
            if stage == kind:
                write()
            return {"records": []} if kind == "list" else {"value": "fixture"}
        return perform

    vault = SimpleNamespace(**{kind: operation(kind) for kind in ("list", "reveal", "save", "delete")})

    def create(*_args, **_kwargs):
        if stage == "initialize":
            write()
        return vault

    action = "list" if stage == "initialize" else stage
    values = {"id": "fixture"} if action in {"reveal", "delete"} else {"label": "Fixture", "value": "fixture"} if action == "save" else {}
    if entry == "tool":
        monkeypatch.setattr("cirno_core.agent.tools.credential.Credentials", create)
        action = {"reveal": "read", "save": "store"}.get(action, action)
        pending = CredentialTool().execute(action, **values)
    else:
        monkeypatch.setattr("cirno_server.webui.workbench_api.Credentials", create)
        monkeypatch.setattr("cirno_server.webui.workbench_api.Terminals", lambda *, state_dir=None: SimpleNamespace())
        pending = WorkbenchAPI(None, None).action({"action": "credentials." + action, "values": values})
    task = asyncio.create_task(pending)
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.01)
        assert not done, "Credentials returned while accepted storage work was still running"
    finally:
        release.set()
        await asyncio.to_thread(completed.wait, 1)
        await asyncio.gather(task, return_exceptions=True)
    assert marker.read_text() == "settled"
    assert task.cancelled()
