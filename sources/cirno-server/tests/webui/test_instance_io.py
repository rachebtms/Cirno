"""Instance database initialization cannot block unrelated gateway work."""

import asyncio
from threading import Event

import pytest

from cirno_core.agent.tools.credential import CredentialTool
from cirno_core.agent.tools.instance_features import NodeTool
from cirno_core.storage.instance import InstanceData
from cirno_server.webui.instance_api import instance_action
from cirno_server.webui.workbench_api import WorkbenchAPI


@pytest.mark.parametrize("entry", ["instance", "credentials", "credential_tool", "node_tool"])
async def test_database_initialization_keeps_the_event_loop_responsive(tmp_path, monkeypatch, entry):
    loop = asyncio.get_running_loop()
    initialize = InstanceData.__init__

    def delayed(self, state_dir=None):
        responsive = Event()
        loop.call_soon_threadsafe(responsive.set)
        assert responsive.wait(1), "Database setup blocked the gateway event loop"
        initialize(self, state_dir or tmp_path)

    monkeypatch.setattr(InstanceData, "__init__", delayed)
    if entry == "instance":
        await instance_action({"action": "nodes.list"}, sessions=None, bus=None)
    elif entry == "credentials":
        await WorkbenchAPI(None, None).action({"action": "credentials.list"})
    elif entry == "credential_tool":
        await CredentialTool().execute("list")
    else:
        await NodeTool().execute("list")
