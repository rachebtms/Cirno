"""Newly installed channel code is loaded only after restarting the server."""

import json
from unittest.mock import MagicMock

from cirno_server.channels.contracts import ChannelSetupSpec
from cirno_server.channels.plugin import ChannelPlugin
from cirno_server.features import service


def test_enable_saves_config_without_importing_newly_installed_runtime(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    plugin = ChannelPlugin(
        name="fixture", display_name="Fixture", runtime="missing.fixture:Channel",
        dependencies=("fixture-sdk>=1",), setup=ChannelSetupSpec(fields={}),
    )
    monkeypatch.setattr("cirno_server.channels.registry.discover_plugins", lambda: {"fixture": plugin})
    monkeypatch.setattr(service, "optional_dependency_groups", lambda: {})
    installed = False

    def install(*args, **kwargs):
        nonlocal installed
        installed = True
        return service.InstallResult(True, "Fixture", ["fixture-installer"])

    monkeypatch.setattr(service, "extra_installed", lambda *args: installed)
    monkeypatch.setattr(service, "install_extra", install)
    load = MagicMock(side_effect=AssertionError("new SDK loaded before restart"))
    monkeypatch.setattr(ChannelPlugin, "load_channel_class", load)
    result = service.enable_optional_feature("fixture", config_path=path)
    load.assert_not_called()
    assert json.loads(path.read_text())["channels"]["fixture"]["enabled"] is True
    assert result["requires_restart"] is True
    assert result["last_action"]["dependencies_installed"] is True


def test_enable_does_not_save_unavailable_dependencies_after_success_exit(tmp_path, monkeypatch):
    import pytest

    path = tmp_path / "config.json"
    plugin = ChannelPlugin(
        name="fixture", display_name="Fixture", runtime="missing.fixture:Channel",
        dependencies=("fixture-sdk>=1",), setup=ChannelSetupSpec(fields={}),
    )
    monkeypatch.setattr("cirno_server.channels.registry.discover_plugins", lambda: {"fixture": plugin})
    monkeypatch.setattr(service, "optional_dependency_groups", lambda: {})
    monkeypatch.setattr(service, "extra_installed", lambda *args: False)
    monkeypatch.setattr(service, "install_extra", lambda *args, **kwargs:
                        service.InstallResult(True, "Fixture", ["fixture-installer"]))
    with pytest.raises(service.OptionalFeatureError, match="dependencies are still unavailable"):
        service.enable_optional_feature("fixture", config_path=path)
    assert not path.exists()
