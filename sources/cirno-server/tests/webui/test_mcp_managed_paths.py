"""Managed MCP cleanup must not acquire user data through symbolic links."""

from pathlib import Path

import pytest
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp.actions import mcp_presets_action
from cirno_server.webui.mcp.contracts import McpPresetError
from cirno_server.webui.mcp.fields import _with_managed_stdio_cwd, remove_managed_stdio_cwd


@pytest.fixture
def instance(tmp_path, monkeypatch):
    path = tmp_path / "instance" / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    save_config(config, path)
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", path)
    return path


def symlink(path: Path, target: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Directory symlinks unavailable: {exc}")


@pytest.mark.parametrize("configured_path", ["managed", "target"])
def test_leaf_symlink_cannot_turn_its_target_into_managed_data(instance, tmp_path, configured_path):
    target = tmp_path / "user-data"
    target.mkdir()
    document = target / "keep.txt"
    document.write_text("User document")
    managed = instance.parent / "state" / "mcp" / "fixture"
    symlink(managed, target)
    cfg = MCPServerConfig(type="stdio", command="fixture", cwd=str(managed if configured_path == "managed" else target))
    removed = remove_managed_stdio_cwd("fixture", cfg)
    assert document.read_text() == "User document"
    assert removed is (configured_path == "managed")
    assert managed.is_symlink() is (configured_path == "target")


def test_preset_creation_does_not_adopt_an_existing_leaf_symlink(instance, tmp_path):
    target = tmp_path / "user-data"
    target.mkdir()
    document = target / "keep.txt"
    document.write_text("User document")
    managed = instance.parent / "state" / "mcp" / "fixture"
    symlink(managed, target)
    with pytest.raises(McpPresetError, match="symbolic link"):
        _with_managed_stdio_cwd("fixture", MCPServerConfig(type="stdio", command="fixture"))
    assert document.read_text() == "User document"
    assert managed.is_symlink()


@pytest.mark.parametrize("operation", ["create", "remove"])
def test_symlinked_runtime_root_cannot_adopt_an_outside_directory(instance, tmp_path, operation):
    outside = tmp_path / "outside"
    protected = outside / "fixture"
    protected.mkdir(parents=True)
    document = protected / "keep.txt"
    document.write_text("User document")
    symlink(instance.parent / "state" / "mcp", outside)
    cfg = MCPServerConfig(type="stdio", command="fixture", cwd=str(protected) if operation == "remove" else "")
    with pytest.raises(McpPresetError, match="runtime directory"):
        if operation == "create":
            _with_managed_stdio_cwd("fixture", cfg)
        else:
            remove_managed_stdio_cwd("fixture", cfg)
    assert document.read_text() == "User document"


def test_managed_cleanup_rejects_a_name_that_escapes_its_parent(instance):
    target = instance.parent / "state" / "user-data"
    target.mkdir(parents=True)
    document = target / "keep.txt"
    document.write_text("User document")
    with pytest.raises(McpPresetError, match="invalid MCP"):
        remove_managed_stdio_cwd("../user-data", MCPServerConfig(type="stdio", command="fixture", cwd=str(target)))
    assert document.read_text() == "User document"


def test_preset_runtime_directory_belongs_to_its_explicit_config(instance):
    other = instance.parent.parent / "other" / "config.json"
    save_config(load_config(instance), other)
    mcp_presets_action("enable", {"name": ["playwright"]}, config_path=other)
    cwd = Path(load_config(other).tools.mcp_servers["playwright"].cwd)
    assert cwd == other.parent / "state" / "mcp" / "playwright"
    assert not (instance.parent / "state" / "mcp" / "playwright").exists()
    (cwd / "cache.txt").write_text("Managed cache")
    payload = mcp_presets_action("remove", {"name": ["playwright"]}, config_path=other)
    assert payload["last_action"]["managed_paths_removed"] == ["runtime:mcp/playwright"]
    assert not cwd.exists()
