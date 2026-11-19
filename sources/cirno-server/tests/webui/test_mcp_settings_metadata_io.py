"""Settings metadata I/O runs off-loop and retains accepted filesystem work."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_core.config.tools import MCPServerConfig
from cirno_core.runtime.admission import RuntimeAdmission, RuntimeBusyError
from cirno_server.webui.mcp import actions, inspection
from cirno_server.webui.settings.services import WebUISettingsConfig


@pytest.fixture
def instance(tmp_path):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    config.tools.mcp_servers["fixture"] = MCPServerConfig(
        type="streamableHttp", url="https://fixture.test/mcp"
    )
    save_config(config, path)
    return path


async def test_catalog_io_uses_a_worker_but_runtime_callback_stays_on_loop(instance, monkeypatch):
    loop = asyncio.get_running_loop()
    main_thread = threading.get_ident()
    statuses = {"fixture": "connecting"}
    release = threading.Event()
    observed = []

    def changed():
        statuses["fixture"] = "failed"
        release.set()

    def runtime_status():
        assert threading.get_ident() == main_thread
        observed.append("runtime")
        return statuses

    def catalog(**kwargs):
        assert threading.get_ident() != main_thread, (
            "Catalog filesystem work blocked the event loop"
        )
        observed.append("catalog")
        loop.call_soon_threadsafe(changed)
        assert release.wait(1), "Runtime status could not advance while catalog I/O was pending"
        payload = {
            "presets": [{"name": "fixture", "installed": True, "configured": True}],
            "installed_count": 1,
        }
        return actions.attach_mcp_runtime_status(payload, kwargs.get("runtime_status"))

    monkeypatch.setattr(actions, "mcp_presets_payload", catalog)
    payload = await actions.mcp_presets_settings_action(
        None, {}, config=WebUISettingsConfig(instance), mcp_runtime_status=runtime_status
    )
    assert payload["presets"][0]["runtime_status"] == "failed"
    assert observed == ["catalog", "runtime"]


@pytest.mark.parametrize("missing_dependency", [False, True])
async def test_inspection_preparation_and_projection_stay_off_loop(
    instance, monkeypatch, missing_dependency
):
    main_thread = threading.get_ident()
    original_load = inspection.load_config
    observed = []

    def load(*args, **kwargs):
        assert threading.get_ident() != main_thread, "Inspection config read blocked the event loop"
        observed.append("load")
        config = original_load(*args, **kwargs)
        if missing_dependency:
            config.tools.mcp_servers["fixture"] = MCPServerConfig(
                type="stdio", command="fixture-command"
            )
        return config

    def available(_command, **_context):
        assert threading.get_ident() != main_thread, "Command discovery blocked the event loop"
        return False

    def catalog(**kwargs):
        assert threading.get_ident() != main_thread, (
            "Inspection catalog projection blocked the event loop"
        )
        observed.append("catalog")
        return {"presets": [{"name": "fixture"}], "last_action": kwargs["last_action"]}

    async def close():
        assert threading.get_ident() == main_thread
        observed.append("close")

    async def connect(*args, **kwargs):
        assert threading.get_ident() == main_thread
        observed.append("connect")
        return {"fixture": SimpleNamespace(aclose=close)}

    monkeypatch.setattr(inspection, "load_config", load)
    monkeypatch.setattr(inspection, "command_available", available)
    monkeypatch.setattr(inspection, "mcp_presets_payload", catalog)
    monkeypatch.setattr("cirno_core.agent.tools.mcp.connector.connect_mcp_servers", connect)
    receipt = await inspection.mcp_presets_test_action({"name": ["fixture"]}, config_path=instance)
    assert receipt["last_action"]["ok"] is not missing_dependency
    assert observed == (
        ["load", "load", "catalog"]
        if missing_dependency else ["load", "connect", "close", "load", "catalog"]
    )


@pytest.mark.parametrize("stage", ["catalog", "inspection-prepare", "inspection-projection"])
@pytest.mark.parametrize("fails", [False, True])
async def test_cancelled_settings_metadata_waits_for_accepted_filesystem_work(
    instance, tmp_path, monkeypatch, stage, fails
):
    loop = asyncio.get_running_loop()
    main_thread = threading.get_ident()
    started = asyncio.Event()
    release = threading.Event()
    completed = threading.Event()
    closed = asyncio.Event()
    marker = tmp_path / "owned-metadata.txt"
    original_load = inspection.load_config

    def work(result):
        loop.call_soon_threadsafe(started.set)
        try:
            assert threading.get_ident() != main_thread, "Metadata worker ran on the event loop"
            assert release.wait(2), "Fixture did not release metadata work"
            marker.write_text("Accepted metadata side effect finished")
            if fails:
                raise OSError("Fixture metadata failure")
            return result()
        finally:
            completed.set()

    async def close():
        closed.set()

    transport = AsyncMock(return_value={"fixture": SimpleNamespace(aclose=close)})
    monkeypatch.setattr("cirno_core.agent.tools.mcp.connector.connect_mcp_servers", transport)
    if stage == "catalog":
        monkeypatch.setattr(
            actions,
            "mcp_presets_payload",
            lambda **kwargs: work(lambda: {"presets": [], "installed_count": 0}),
        )
        request = actions.mcp_presets_settings_action(
            None, {}, config=WebUISettingsConfig(instance)
        )
    elif stage == "inspection-prepare":
        monkeypatch.setattr(
            inspection,
            "load_config",
            lambda *args, **kwargs: work(lambda: original_load(*args, **kwargs)),
        )
        request = inspection.mcp_presets_test_action({"name": ["fixture"]}, config_path=instance)
    else:

        def catalog(**kwargs):
            assert closed.is_set(), "Inspection projected metadata before closing its connection"
            return work(
                lambda: {"presets": [{"name": "fixture"}], "last_action": kwargs["last_action"]}
            )

        monkeypatch.setattr(inspection, "mcp_presets_payload", catalog)
        request = inspection.mcp_presets_test_action({"name": ["fixture"]}, config_path=instance)
    admission = RuntimeAdmission()

    async def dispatch():
        with admission.activity():
            return await request

    task = asyncio.create_task(dispatch())
    try:
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        pending = not task.done()
        with pytest.raises(RuntimeBusyError), admission.pause_if_idle(lambda: False):
            pytest.fail(
                "Cancelled metadata request released maintenance admission before its worker"
            )
    finally:
        release.set()
        outcomes = await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(completed.wait, 2)
    with admission.pause_if_idle(lambda: False):
        pass
    assert pending, "Settings request detached accepted filesystem work"
    assert isinstance(outcomes[0], asyncio.CancelledError)
    assert marker.read_text() == "Accepted metadata side effect finished"
    assert transport.await_count == (1 if stage == "inspection-projection" else 0)


@pytest.mark.parametrize("entry", ["catalog", "inspection"])
async def test_default_metadata_read_keeps_the_instance_selected_before_worker_io(
    tmp_path, monkeypatch, entry
):
    paths = [tmp_path / name / "config.json" for name in ("first", "second")]
    for name, path in zip(("first", "second"), paths, strict=True):
        config = Config()
        config.agents.defaults.workspace = str(tmp_path / "workspace")
        config.tools.mcp_servers[name] = MCPServerConfig(
            type="streamableHttp", url=f"https://{name}.fixture.test/mcp"
        )
        save_config(config, path)
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", paths[0])
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()

    def hold(operation, *args, **kwargs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(2), "Fixture did not release metadata read"
        return operation(*args, **kwargs)

    async def connect(*args, **kwargs):
        return {"first": SimpleNamespace(aclose=AsyncMock())}

    monkeypatch.setattr("cirno_core.agent.tools.mcp.connector.connect_mcp_servers", connect)
    if entry == "catalog":
        catalog = actions.mcp_presets_payload
        monkeypatch.setattr(
            actions, "mcp_presets_payload", lambda **kwargs: hold(catalog, **kwargs)
        )
        request = actions.mcp_presets_settings_action(None, {})
    else:
        load = inspection.load_config
        monkeypatch.setattr(
            inspection, "load_config", lambda *args, **kwargs: hold(load, *args, **kwargs)
        )
        request = inspection.mcp_presets_test_action({"name": ["first"]})
    task = asyncio.create_task(request)
    try:
        await asyncio.wait_for(started.wait(), 1)
        monkeypatch.setattr("cirno_core.config.loader._current_config_path", paths[1])
        release.set()
        payload = await task
        installed = {row["name"] for row in payload["presets"] if row["installed"]}
        assert installed == {"first"}
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
