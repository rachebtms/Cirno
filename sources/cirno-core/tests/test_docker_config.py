"""Exercise the Docker initializer that the container entrypoint invokes."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cirno.channels.websocket.runtime import WebSocketConfig
from cirno.config.loader import load_config, resolve_config_env_vars


def _initialize(path: Path, web_token: str = "", api_key: str = "") -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, CIRNO_WEB_TOKEN=web_token, CIRNO_API_KEY=api_key)
    return subprocess.run(
        [sys.executable, "-m", "cirno.cli.docker_bootstrap", str(path)],
        env=env, capture_output=True, text=True,
    )


def test_first_boot_generates_valid_container_config(tmp_path):
    path = tmp_path / "instance" / "config.json"
    result = _initialize(path)
    assert result.returncode == 0, result.stderr
    config = resolve_config_env_vars(load_config(path))
    ws = WebSocketConfig.model_validate(config.channels.model_dump()["websocket"])
    assert config.gateway.host == ws.host == "0.0.0.0"
    assert ws.enabled and ws.websocket_requires_token
    assert ws.browser_setup
    assert not ws.token_issue_secret
    assert "complete setup in your browser" in result.stdout
    assert "password:" not in result.stdout


@pytest.mark.parametrize("secret", ['review&secret', 'review|secret', 'review"secret', r'review\secret'])
def test_custom_secrets_survive_json_serialization(tmp_path, secret):
    path = tmp_path / "config.json"
    result = _initialize(path, secret, secret)
    assert result.returncode == 0, result.stderr
    config = resolve_config_env_vars(load_config(path))
    ws = WebSocketConfig.model_validate(config.channels.model_dump()["websocket"])
    assert ws.token_issue_secret == secret
    assert not ws.browser_setup
    assert secret not in result.stdout


def test_restart_preserves_user_settings_and_credentials(tmp_path):
    path = tmp_path / "config.json"
    assert _initialize(path, "original-web", "original-api").returncode == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    data["providers"]["custom"] = {"apiKey": "provider-key", "apiBase": "http://model:8000/v1"}
    path.write_text(json.dumps(data), encoding="utf-8")
    previous = path.read_bytes()
    result = _initialize(path, "replacement-web", "replacement-api")
    assert result.returncode == 0, result.stderr
    assert path.read_bytes() == previous
    assert "replacement-web" not in result.stdout
    assert "replacement-api" not in result.stdout


def test_failed_write_does_not_leave_an_existing_config(tmp_path):
    # A bind mount can be unwritable. Force failure at the actual atomic
    # replacement boundary rather than only validating the input template.
    from unittest.mock import patch

    from cirno.cli.docker_bootstrap import initialize_config

    path = tmp_path / "config.json"
    with patch.object(Path, "replace", side_effect=PermissionError("read-only mount")):
        with pytest.raises(PermissionError, match="read-only mount"):
            initialize_config(path)
    assert not path.exists()
    assert not list(tmp_path.glob("*.tmp"))
