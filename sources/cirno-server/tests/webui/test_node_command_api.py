"""Direct Node commands preserve process results across the WebUI boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from cirno_core.nodes.commands import CommandResult
from cirno_core.storage.instance import InstanceData
from cirno_server.webui.instance_api import instance_action


@pytest.mark.parametrize(("values", "expected"), [({}, 600), ({"timeout": 700}, 700), ({"max_runtime": 800}, 800), ({"max_runtime": 0}, None)])
async def test_node_dialog_uses_its_own_instance_shell_runtime(tmp_path, monkeypatch, values, expected):
    from cirno_core.config.loader import save_config
    from cirno_core.config.schema import Config

    path = tmp_path / "instance" / "config.json"
    save_config(Config.model_validate({"tools": {"exec": {"max_runtime": 600, "max_runtime_limit": 0}}}), path)
    execute = AsyncMock(return_value=CommandResult("done", "", 0))
    monkeypatch.setattr("cirno_server.webui.instance_api.Nodes", lambda data: SimpleNamespace(execute_command=execute))
    await instance_action({"action": "nodes.execute", "values": {"id": "gpu", "command": "run-once", **values}},
                          sessions=None, bus=None, config_path=path)
    execute.assert_awaited_once_with("gpu", "run-once", timeout=expected)


@pytest.mark.parametrize("values", [{"timeout": 601}, {"max_runtime": 0}, {"timeout": True}, {"timeout": "600"}, {"timeout": 10, "max_runtime": 20}])
async def test_invalid_node_dialog_runtime_never_runs_the_command(tmp_path, monkeypatch, values):
    from cirno_core.config.loader import save_config
    from cirno_core.config.schema import Config

    path = tmp_path / "config.json"
    save_config(Config.model_validate({"tools": {"exec": {"max_runtime_limit": 600}}}), path)
    execute = AsyncMock()
    monkeypatch.setattr("cirno_server.webui.instance_api.Nodes", lambda data: SimpleNamespace(execute_command=execute))
    with pytest.raises(ValueError):
        await instance_action({"action": "nodes.execute", "values": {"id": "gpu", "command": "write", **values}},
                              sessions=None, bus=None, config_path=path)
    execute.assert_not_awaited()


async def test_nonzero_command_exit_is_structured_and_keeps_the_legacy_output(tmp_path, monkeypatch):
    data = InstanceData(tmp_path)
    execute = AsyncMock(return_value=CommandResult("partial stdout", "missing key file", 2))
    monkeypatch.setattr("cirno_server.webui.instance_api.InstanceData", lambda _state_dir=None: data)
    monkeypatch.setattr("cirno_server.webui.instance_api.Nodes", lambda _: SimpleNamespace(execute_command=execute))
    result = await instance_action({"action": "nodes.execute", "values": {"id": "gpu", "command": "ssh-keygen -lf missing", "timeout": 30}}, sessions=None, bus=None)
    assert result == {"stdout": "partial stdout", "stderr": "missing key file", "exit_code": 2, "output": "partial stdout\nmissing key file"}
    execute.assert_awaited_once_with("gpu", "ssh-keygen -lf missing", timeout=30)


async def test_node_monitoring_settings_save_without_restart_and_reappear_in_catalog(tmp_path, monkeypatch):
    import pytest
    from cirno_core.nodes.service import Nodes
    from pydantic import ValidationError

    data = InstanceData(tmp_path)
    monkeypatch.setattr("cirno_server.webui.instance_api.InstanceData", lambda _state_dir=None: data)
    result = await instance_action({"action": "nodes.settings.save", "values": {"poll_interval_seconds": 0}}, sessions=None, bus=None)
    assert result["job_settings"] == {"poll_interval_seconds": 0, "retention_days": 30}
    await instance_action({"action": "nodes.settings.save", "values": {"retention_days": 7}}, sessions=None, bus=None)
    assert Nodes(InstanceData(tmp_path)).catalog()["job_settings"] == {"poll_interval_seconds": 0, "retention_days": 7}
    with pytest.raises(ValidationError):
        await instance_action({"action": "nodes.settings.save", "values": {"retention_days": -1}}, sessions=None, bus=None)
    assert Nodes(data).catalog()["job_settings"]["retention_days"] == 7


async def test_confirmed_command_after_disconnect_keeps_result_and_warning_in_webui(tmp_path, monkeypatch):
    data = InstanceData(tmp_path)
    execute = AsyncMock(return_value=CommandResult("finished output", "SSH connection closed", 0, "Completion receipt confirmed; do not repeat."))
    monkeypatch.setattr("cirno_server.webui.instance_api.InstanceData", lambda _state_dir=None: data)
    monkeypatch.setattr("cirno_server.webui.instance_api.Nodes", lambda _: SimpleNamespace(execute_command=execute))
    result = await instance_action({"action": "nodes.execute", "values": {"id": "gpu", "command": "run-once"}}, sessions=None, bus=None)
    assert result["exit_code"] == 0 and result["stdout"] == "finished output"
    assert result["connection_warning"] in result["output"]
    execute.assert_awaited_once()
