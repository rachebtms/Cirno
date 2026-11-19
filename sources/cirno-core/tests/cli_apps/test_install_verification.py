"""Successful package exit is separate from a usable CLI entry point."""

import subprocess

import pytest
from cirno_core.apps.cli.service import CliAppManager


@pytest.mark.parametrize("action,bundled", [("install", False), ("update", False), ("update", True)])
def test_missing_executable_is_not_a_successful_ready_install(tmp_path, monkeypatch, action, bundled):
    monkeypatch.setattr("cirno_core.apps.cli.paths.get_home_path", lambda: tmp_path)
    app = {"name": "research", "display_name": "Research", "entry_point": "research-cli",
           "package_manager": "bundled" if bundled else "brew",
           "install_cmd": "brew install research", "update_cmd": "brew upgrade research"}
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / "state")
    monkeypatch.setattr(manager.registry, "get_app", lambda *args, **kwargs: app)
    monkeypatch.setattr(manager.registry, "catalog", lambda **kwargs: ([app], None))
    monkeypatch.setattr(manager.commands, "which", lambda name: None)
    monkeypatch.setattr(manager.commands, "_run_argv", lambda argv, **kwargs:
                        subprocess.CompletedProcess(argv, 0, "done", ""))
    monkeypatch.setattr(manager, "_fetch_skill_content", lambda app: None)
    if action == "update":
        manager.installed.put("research", {"entry_point": "research-cli"})
    result = getattr(manager, action)("research")
    assert result["last_action"]["ok"] is False
    assert result["last_action"]["verification_failed"] == ["entry_point_available"]
    assert result["apps"][0]["available"] is False
    assert result["apps"][0]["installed"] is True
    assert "research" in manager.installed.read(), "Keep package identity available for repair/uninstall"
