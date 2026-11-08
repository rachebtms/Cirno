from __future__ import annotations

import asyncio

import pytest
from cirno_core.bus.queue import MessageBus
from cirno_core.config.schema import Config
from cirno_server.channels.base import BaseChannel
from cirno_server.channels.contracts import (
    ChannelInstanceSpec,
    ChannelManagementSpec,
    ChannelSetupSpec,
)
from cirno_server.channels.manager import ChannelManager
from cirno_server.channels.plugin import ChannelPlugin


class _HotChannel(BaseChannel):
    name = "hot"
    display_name = "Hot"

    def __init__(self, config, bus):
        super().__init__(config, bus)
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()

    async def start(self):
        self._running = True
        self.started.set()
        await self.stopped.wait()

    async def stop(self):
        self._running = False
        self.stopped.set()

    async def send(self, msg):  # pragma: no cover - not used by this test
        raise AssertionError("send should not be called")


class _MultiHotChannel(_HotChannel):
    name = "multi"
    display_name = "Multi"

class _AliasHotChannel(_HotChannel):
    """Package descriptor alias that claims another channel's runtime namespace."""

    name = "hot"
    display_name = "Alias"


def _multi_instance_specs(section, *, enabled_only=True):
    instances = section.get("instances", []) if isinstance(section, dict) else []
    return [
        ChannelInstanceSpec(
            instance_id=item["id"],
            config=item,
        )
        for item in instances
        if not enabled_only or item.get("enabled", False)
    ]


def _plugin(channel_cls: type[BaseChannel], *, multi_instance: bool = False) -> ChannelPlugin:
    runtime_attr = f"_runtime_{channel_cls.display_name.lower()}"
    globals()[runtime_attr] = channel_cls
    setup = ChannelSetupSpec(fields={}) if multi_instance else None
    management = (
        ChannelManagementSpec(
            multi_instance=True,
            instance_specs=_multi_instance_specs,
            update_instance_config=lambda section, values, *, instance_id="default": values,
            runtime_name=lambda name, instance_id: (
                name if instance_id == "default" else f"{name}.{instance_id}"
            ),
        )
        if multi_instance
        else ChannelManagementSpec()
    )
    return ChannelPlugin(
        name=channel_cls.name,
        display_name=channel_cls.display_name,
        runtime=f"{__name__}:{runtime_attr}",
        setup=setup,
        management=management,
    )


def _stub_registry(monkeypatch, *plugins: ChannelPlugin) -> None:
    by_name = {plugin.name: plugin for plugin in plugins}
    monkeypatch.setattr(
        "cirno_server.channels.registry.discover_plugins",
        lambda enabled_names=None: {
            name: plugin
            for name, plugin in by_name.items()
            if enabled_names is None or name in enabled_names
        },
    )


def test_descriptor_rejects_runtime_class_owned_by_another_name():
    plugin = ChannelPlugin(
        name="alias",
        display_name="Alias",
        runtime=f"{__name__}:_AliasHotChannel",
    )

    with pytest.raises(ImportError, match="runtime declares name 'hot'"):
        plugin.load_channel_class()


@pytest.mark.asyncio
async def test_apply_channel_feature_action_starts_and_stops_channel(monkeypatch):
    disabled = Config.model_validate({
        "channels": {
            "websocket": {"enabled": False},
            "hot": {"enabled": False},
        }
    })
    enabled = Config.model_validate({
        "channels": {
            "websocket": {"enabled": False},
            "hot": {"enabled": True},
        }
    })

    configs = iter([enabled, disabled])
    _stub_registry(monkeypatch, _plugin(_HotChannel))
    monkeypatch.setattr("cirno_core.config.loader.load_config", lambda _path=None: next(configs))

    manager = ChannelManager(disabled, MessageBus())
    manager.runtimes.started = True

    enabled_result = await manager.activation.apply("enable", "hot")

    assert enabled_result["handled"] is True
    assert enabled_result["requires_restart"] is False
    channel = manager.runtimes.channels["hot"]
    await asyncio.wait_for(channel.started.wait(), timeout=1)
    assert channel.is_running is True

    disabled_result = await manager.activation.apply("disable", "hot")

    assert disabled_result["handled"] is True
    assert disabled_result["requires_restart"] is False
    assert "hot" not in manager.runtimes.channels
    assert channel.is_running is False


@pytest.mark.asyncio
async def test_apply_channel_feature_action_keeps_running_channel_when_rebuild_fails(monkeypatch):
    enabled = Config.model_validate({
        "channels": {
            "websocket": {"enabled": False},
            "hot": {"enabled": True},
        }
    })

    _stub_registry(monkeypatch, _plugin(_HotChannel))
    monkeypatch.setattr("cirno_core.config.loader.load_config", lambda _path=None: enabled)

    manager = ChannelManager(enabled, MessageBus())
    old_channel = manager.runtimes.channels["hot"]
    old_channel._running = True

    def fail_build(*_args, **_kwargs):
        raise RuntimeError("invalid replacement config")

    monkeypatch.setattr(manager.activation.factory, "build", fail_build)

    result = await manager.activation.apply("enable", "hot")

    assert result["requires_restart"] is False
    assert result["ok"] is False
    assert manager.runtimes.channels["hot"] is old_channel
    assert old_channel.is_running is True
    assert not old_channel.stopped.is_set()


@pytest.mark.asyncio
async def test_apply_channel_feature_action_uses_channel_runtime_name(monkeypatch):
    config = Config.model_validate({
        "channels": {
            "websocket": {"enabled": False},
            "multi": {
                "enabled": True,
                "instances": [
                    {"id": "default", "enabled": True},
                    {"id": "product", "enabled": True},
                ]
            },
        }
    })

    _stub_registry(monkeypatch, _plugin(_MultiHotChannel, multi_instance=True))
    monkeypatch.setattr("cirno_core.config.loader.load_config", lambda _path=None: config)

    manager = ChannelManager(config, MessageBus())
    product = manager.runtimes.channels["multi.product"]
    product._running = True

    result = await manager.activation.apply("disable", "multi", "product")

    assert result["requires_restart"] is False
    assert "multi" in manager.runtimes.channels
    assert "multi.product" not in manager.runtimes.channels
    assert product.is_running is False


@pytest.mark.asyncio
async def test_default_multi_channel_action_reconciles_only_default_runtime(monkeypatch):
    initial = Config.model_validate({
        "channels": {
            "websocket": {"enabled": False},
            "multi": {
                "enabled": True,
                "instances": [
                    {"id": "default", "enabled": True},
                    {"id": "product", "enabled": True},
                ],
            },
        }
    })
    disabled = Config.model_validate({
        "channels": {
            "websocket": {"enabled": False},
            "multi": {
                "enabled": True,
                "instances": [
                    {"id": "default", "enabled": False},
                    {"id": "product", "enabled": True},
                ],
            },
        }
    })
    enabled = Config.model_validate({
        "channels": {
            "websocket": {"enabled": False},
            "multi": {
                "enabled": True,
                "instances": [
                    {"id": "default", "enabled": True},
                    {"id": "product", "enabled": True},
                ],
            },
        }
    })

    _stub_registry(monkeypatch, _plugin(_MultiHotChannel, multi_instance=True))
    configs = iter([disabled, enabled])
    monkeypatch.setattr("cirno_core.config.loader.load_config", lambda _path=None: next(configs))

    manager = ChannelManager(initial, MessageBus())
    default = manager.runtimes.channels["multi"]
    product = manager.runtimes.channels["multi.product"]

    disabled_result = await manager.activation.apply("disable", "multi")

    assert disabled_result["requires_restart"] is False
    assert set(manager.runtimes.channels) == {"multi.product"}
    assert default.stopped.is_set()
    assert not product.stopped.is_set()

    enabled_result = await manager.activation.apply("enable", "multi")

    assert enabled_result["requires_restart"] is False
    assert set(manager.runtimes.channels) == {"multi", "multi.product"}
    assert manager.runtimes.channels["multi.product"] is product


async def test_parallel_reconfiguration_never_leaves_an_unowned_running_channel(tmp_path, monkeypatch):
    config = Config.model_validate({"channels": {"websocket": {"enabled": False}, "hot": {"enabled": True}}})
    _stub_registry(monkeypatch, _plugin(_HotChannel))
    monkeypatch.setattr("cirno_core.config.loader.load_config", lambda _path=None: config)
    manager = ChannelManager(config, MessageBus(), config_path=tmp_path / "config.json")
    manager.runtimes.started = True
    old = manager.runtimes.channels["hot"]
    old._running = True
    entered, release = asyncio.Event(), asyncio.Event()
    stop_old, build, start = old.stop, manager.activation.factory.build, manager.runtimes.start_task
    created, started = [], []

    async def gated_stop():
        entered.set()
        await release.wait()
        await stop_old()

    def record_build(*args, **kwargs):
        channel = build(*args, **kwargs)
        created.append(channel)
        return channel

    def record_start(*args, **kwargs):
        task = start(*args, **kwargs)
        started.append(task)
        return task

    monkeypatch.setattr(old, "stop", gated_stop)
    monkeypatch.setattr(manager.activation.factory, "build", record_build)
    monkeypatch.setattr(manager.runtimes, "start_task", record_start)
    first = asyncio.create_task(manager.activation.apply("enable", "hot"))
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        second = asyncio.create_task(manager.activation.apply("enable", "hot"))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, second)
        assert sum(channel.is_running for channel in created) == 1
        assert manager.runtimes.channels["hot"].is_running
    finally:
        release.set()
        await asyncio.gather(*(task for task in (first, second) if task is not None), return_exceptions=True)
        await manager.stop_all()
        for channel in created:
            await channel.stop()
        await asyncio.gather(*started, return_exceptions=True)


async def test_live_reconfiguration_reads_the_owning_instance_config(tmp_path, monkeypatch):
    from cirno_core.config.loader import save_config

    _stub_registry(monkeypatch, _plugin(_HotChannel))
    disabled = Config.model_validate({"channels": {"websocket": {"enabled": False}, "hot": {"enabled": False}}})
    enabled = Config.model_validate({"channels": {"websocket": {"enabled": False}, "hot": {"enabled": True}}})
    custom_path = tmp_path / "other-instance" / "config.json"
    save_config(enabled, custom_path)
    manager = ChannelManager(disabled, MessageBus(), config_path=custom_path)
    try:
        result = await manager.activation.apply("enable", "hot")
        assert result["ok"] is True
        assert "hot" in manager.runtimes.channels
    finally:
        await manager.stop_all()


async def test_runtime_import_failure_reports_status_and_exception_diagnostics(monkeypatch):
    from loguru import logger

    _stub_registry(monkeypatch, _plugin(_HotChannel))
    disabled = Config.model_validate({"channels": {"websocket": {"enabled": False}, "hot": {"enabled": False}}})
    enabled = Config.model_validate({"channels": {"websocket": {"enabled": False}, "hot": {"enabled": True}}})
    monkeypatch.setattr("cirno_core.config.loader.load_config", lambda _path=None: enabled)
    manager = ChannelManager(disabled, MessageBus())

    def broken_runtime(_plugin):
        raise ImportError("Channel runtime dependency is unavailable")

    monkeypatch.setattr(ChannelPlugin, "load_channel_class", broken_runtime)
    records = []
    sink = logger.add(lambda message: records.append(message.record), level="ERROR")
    try:
        result = await manager.activation.apply("enable", "hot")
        assert result["ok"] is False
        assert manager.runtimes.status()["hot"]["state"] == "failed"
        assert any(record["exception"] and record["exception"].type is ImportError for record in records)
    finally:
        logger.remove(sink)
        await manager.stop_all()
