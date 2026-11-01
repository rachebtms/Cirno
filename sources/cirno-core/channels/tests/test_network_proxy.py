"""Shared proxy ownership at channel construction and setup boundaries."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cirno.bus.queue import MessageBus
from cirno.channels.contracts import ChannelValidationContext
from cirno.channels.manager import ChannelManager
from cirno.channels.registry import load_channel_plugin
from cirno.config.network import NetworkConfig
from cirno.config.schema import Config

_CHANNEL_VALUES = {
    "telegram": {"token": "123456:abcdefghijklmnopqrstuvwxyz"},
}


@pytest.mark.parametrize("name", _CHANNEL_VALUES)
def test_setup_refuses_proxy_opt_in_without_shared_address(name, monkeypatch) -> None:
    def fail_client(*_args, **_kwargs):
        pytest.fail("missing shared proxy must not fall back to a direct connection")

    monkeypatch.setattr("httpx.Client", fail_client)
    validator = load_channel_plugin(name).setup.validator

    result = validator(
        {**_CHANNEL_VALUES[name], "useProxy": True}, ChannelValidationContext(),
    )

    assert result["status"] == "invalid"
    assert result["can_enable"] is False
    proxy_check = next(check for check in result["checks"] if check["id"] == "network_proxy")
    assert proxy_check["status"] == "fail"
    assert "Advanced" in proxy_check["message"]


@pytest.mark.parametrize(
    ("name", "request_method", "response"),
    [
        ("telegram", "_get_me", {"ok": True, "result": {"id": 42}}),
    ],
)
@pytest.mark.parametrize("use_proxy", [True, False, "false"])
def test_identity_validation_respects_shared_proxy_opt_in(
    name, request_method, response, use_proxy, monkeypatch,
) -> None:
    module = importlib.import_module(f"cirno.channels.{name}.validation")
    proxies = []

    def request(_target, proxy=None, **_kwargs):
        proxies.append(proxy)
        return response

    monkeypatch.setattr(module, request_method, request)
    network = NetworkConfig(proxy="http://user:pass@127.0.0.1:7890")

    result = module.validate(
        {**_CHANNEL_VALUES[name], "useProxy": use_proxy},
        ChannelValidationContext(network=network),
    )

    assert result["status"] == "connected"
    assert proxies == [network.proxy if use_proxy is True else None]
    assert network.proxy not in str(result)


@pytest.mark.parametrize("name", _CHANNEL_VALUES)
def test_runtime_refuses_proxy_opt_in_without_shared_address(name) -> None:
    pytest.importorskip(f"cirno.channels.{name}.runtime", exc_type=ImportError)
    channel_cls = load_channel_plugin(name).load_channel_class()

    with pytest.raises(ValueError, match="Advanced"):
        channel_cls({"useProxy": True}, MessageBus(), network=NetworkConfig())


@pytest.mark.parametrize("name", _CHANNEL_VALUES)
@pytest.mark.parametrize("use_proxy", [True, False])
def test_manager_constructs_proxy_capable_builtin_from_descriptor(
    name, use_proxy, monkeypatch, tmp_path,
) -> None:
    pytest.importorskip(f"cirno.channels.{name}.runtime", exc_type=ImportError)
    plugin = load_channel_plugin(name)
    monkeypatch.setattr("cirno.channels.registry.discover_plugins", lambda: {name: plugin})
    monkeypatch.setattr("cirno.features.service.extra_installed", lambda *_args: True)
    config = Config.model_validate({
        "network": {"proxy": "http://127.0.0.1:7890"},
        "channels": {
            name: {**_CHANNEL_VALUES[name], "enabled": True, "useProxy": use_proxy},
        },
    })

    manager = ChannelManager(config, MessageBus(), config_path=tmp_path / "config.json")

    channel = manager.channels[name]
    assert isinstance(channel, plugin.load_channel_class())
    assert channel.uses_shared_proxy is True
    assert channel.network is config.network
    assert channel._proxy == (config.network.proxy if use_proxy else None)




@pytest.mark.parametrize(("name", "request_method"), [("telegram", "_get_me")])
def test_identity_validation_does_not_expose_shared_proxy_in_errors(name, request_method, monkeypatch) -> None:
    module = importlib.import_module(f"cirno.channels.{name}.validation")
    network = NetworkConfig(proxy="http://user:pass@127.0.0.1:7890")

    def fail_request(*_args, **_kwargs):
        raise OSError(f"could not connect through {network.proxy}")

    monkeypatch.setattr(module, request_method, fail_request)
    result = module.validate(
        {**_CHANNEL_VALUES[name], "useProxy": True}, ChannelValidationContext(network=network),
    )

    assert result["status"] == "configured"
    assert result["can_enable"] is True
    assert any(check["status"] == "warn" for check in result["checks"])
    assert network.proxy not in str(result)
    assert "user:pass" not in str(result)
