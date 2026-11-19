"""Installer ownership is shared with setup; no real commands are executed."""

import subprocess

import pytest
from cirno_server.features import service


def test_feature_installer_uses_owned_process_runner(monkeypatch):
    captured = {}

    def owned(arguments, **kwargs):
        captured.update(arguments=arguments, **kwargs)
        return subprocess.CompletedProcess(arguments, 0, "installed", "")

    def unowned(*args, **kwargs):
        kwargs.clear()
        pytest.fail("Installer bypassed process ownership")

    monkeypatch.setattr(service, "run_owned_command", owned, raising=False)
    monkeypatch.setattr(service.subprocess, "run", unowned)
    monkeypatch.setenv("HTTPS_PROXY", "http://fixture-proxy.example:8080")
    monkeypatch.setattr(service, "python_environment", lambda env: {"HTTPS_PROXY": env["HTTPS_PROXY"]})
    result = service.run_install_command(["fixture-installer"])
    assert result.returncode == 0 and result.stdout == "installed"
    assert captured["arguments"] == ["fixture-installer"]
    assert captured["capture_output"] is True and captured["text"] is True
    assert captured["timeout"] == 300
    assert captured["env"]["HTTPS_PROXY"] == "http://fixture-proxy.example:8080"
