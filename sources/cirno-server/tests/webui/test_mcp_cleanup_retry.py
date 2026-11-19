"""Repeated MCP saves reconcile stale credentials without revoking current authorization."""

import json
from types import SimpleNamespace

import pytest
from cirno_core.agent.tools.mcp_oauth import MCPOAuthStorage
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.schema import Config
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp import actions, configuration
from cirno_server.webui.mcp.catalog import mcp_presets_payload
from cirno_server.webui.mcp.cleanup import pending_cleanup_names
from cirno_server.webui.mcp.contracts import McpPresetError
from mcp.shared.auth import OAuthToken


def _query(action, *, auth):
    server = {"type": "streamableHttp", "url": "https://current.fixture.test/mcp"}
    if auth:
        server["auth"] = "oauth"
    if action == "custom":
        return {
            "name": ["fixture"],
            "transport": [server["type"]],
            "url": [server["url"]],
            "auth": ["oauth" if auth else ""],
        }
    return {"config": [json.dumps({"mcpServers": {"fixture": server}})]}


@pytest.mark.parametrize("action", ["custom", "import", "import-cursor"])
@pytest.mark.parametrize("auth", [False, True])
async def test_identical_save_retries_stale_credential_cleanup_after_earlier_commit(
    tmp_path, monkeypatch, action, auth
):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    config.tools.mcp_servers["fixture"] = MCPServerConfig(
        type="streamableHttp", auth="oauth", url="https://old.fixture.test/mcp"
    )
    save_config(config, path)
    old = MCPOAuthStorage("fixture", "https://old.fixture.test/mcp", config_path=path)
    await old.set_tokens(OAuthToken(access_token="old-fixture-token"))
    query = _query(action, auth=auth)

    def fail_cleanup(*args, **kwargs):
        raise OSError("Fixture credential cleanup failed")

    with monkeypatch.context() as scoped:
        scoped.setattr(configuration, "delete_mcp_oauth_credentials", fail_cleanup)
        receipt = configuration.custom_mcp_action(action, query, config_path=path)["last_action"]
    assert receipt["persisted"] is True and receipt["ok"] is False
    assert load_config(path).tools.mcp_servers["fixture"].url == "https://current.fixture.test/mcp"
    assert (await old.get_tokens()).access_token == "old-fixture-token"

    receipt = configuration.custom_mcp_action(action, query, config_path=path)["last_action"]
    assert receipt["ok"] is True
    assert await old.get_tokens() is None, "Repeated save left obsolete credentials behind"
    await old.set_tokens(OAuthToken(access_token="late-old-fixture-token"))
    assert await old.get_tokens() is None

    if auth:
        current = MCPOAuthStorage("fixture", "https://current.fixture.test/mcp", config_path=path)
        await current.prepare_redirect_uri("https://fixture.test/callback")
        await current.set_tokens(OAuthToken(access_token="current-fixture-token"))
        configuration.custom_mcp_action(action, query, config_path=path)
        assert (await current.get_tokens()).access_token == "current-fixture-token"
        # A preserved entry must retain its write lease/generation, not merely its bytes.
        await current.set_tokens(OAuthToken(access_token="rotated-current-fixture-token"))
        assert (await current.get_tokens()).access_token == "rotated-current-fixture-token"


async def test_configuration_change_preserves_authorization_already_obtained_for_new_url(tmp_path):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    config.tools.mcp_servers["fixture"] = MCPServerConfig(
        type="streamableHttp", auth="oauth", url="https://old.fixture.test/mcp"
    )
    save_config(config, path)
    current = MCPOAuthStorage("fixture", "https://current.fixture.test/mcp", config_path=path)
    await current.prepare_redirect_uri("https://fixture.test/callback")
    await current.set_tokens(OAuthToken(access_token="current-fixture-token"))
    configuration.custom_mcp_action("custom", _query("custom", auth=True), config_path=path)
    assert (await current.get_tokens()).access_token == "current-fixture-token"


async def test_removed_custom_connection_exposes_and_retries_its_orphan_cleanup(
    tmp_path, monkeypatch
):
    path = tmp_path / "config.json"
    cwd = tmp_path / "state" / "mcp" / "fixture"
    cwd.mkdir(parents=True)
    (cwd / "cache.txt").write_text("Old managed runtime")
    user_data = tmp_path / "user-files"
    user_data.mkdir()
    (user_data / "keep.txt").write_text("User data")
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    config.tools.mcp_servers["fixture"] = MCPServerConfig(
        type="stdio", command="fixture", cwd=str(cwd)
    )
    save_config(config, path)
    old = MCPOAuthStorage("fixture", "https://old.fixture.test/mcp", config_path=path)
    await old.set_tokens(OAuthToken(access_token="old-fixture-token"))

    def fail_cleanup(*args, **kwargs):
        raise OSError("Fixture cleanup unavailable")

    with monkeypatch.context() as scoped:
        scoped.setattr(actions, "remove_managed_stdio_cwd", fail_cleanup)
        scoped.setattr(actions, "delete_mcp_oauth_credentials", fail_cleanup)
        actions.mcp_presets_action("remove", {"name": ["fixture"]}, config_path=path)
    # Read a fresh catalog, as after refresh/restart; no transient receipt is retained.
    payload = mcp_presets_payload(config_path=path)
    assert payload.get("cleanup_pending") == ["fixture"]
    assert "old-fixture-token" not in str(payload)
    result = actions.mcp_presets_action(
        "remove", {"name": ["fixture"], "cleanup_only": ["true"]}, config_path=path
    )
    assert result["last_action"]["ok"] is True
    assert result.get("cleanup_pending") == []
    assert not cwd.exists()
    assert await old.get_tokens() is None
    await old.set_tokens(OAuthToken(access_token="late-fixture-token"))
    assert await old.get_tokens() is None
    assert (user_data / "keep.txt").read_text() == "User data"


@pytest.mark.parametrize("flag", ["true", "false", "invalid"])
async def test_cleanup_retry_never_removes_a_connection_created_since_the_receipt(tmp_path, flag):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    config.tools.mcp_servers["fixture"] = MCPServerConfig(
        type="streamableHttp", auth="oauth", url="https://current.fixture.test/mcp"
    )
    save_config(config, path)
    current = MCPOAuthStorage("fixture", "https://current.fixture.test/mcp", config_path=path)
    await current.set_tokens(OAuthToken(access_token="current-fixture-token"))
    with pytest.raises(McpPresetError) as caught:
        actions.mcp_presets_action(
            "remove", {"name": ["fixture"], "cleanup_only": [flag]}, config_path=path
        )
    assert caught.value.status == (409 if flag == "true" else 400)
    assert "fixture" in load_config(path).tools.mcp_servers
    assert (await current.get_tokens()).access_token == "current-fixture-token"


def test_cleanup_discovery_and_retry_preserve_active_plugin_runtime_names(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    config.tools.mcp_servers["manual"] = MCPServerConfig(command="fixture")
    save_config(config, path)
    plugins = [
        SimpleNamespace(name="single", enabled=True, mcp_servers=("server",)),
        SimpleNamespace(name="multi", enabled=True, mcp_servers=("left", "right")),
        SimpleNamespace(name="disabled", enabled=False, mcp_servers=("server",)),
    ]
    root = tmp_path / "state" / "mcp"
    for name in ("manual", "single", "multi--left", "multi--right", "disabled", "orphan"):
        (root / name).mkdir(parents=True)
    assert pending_cleanup_names(load_config(path), plugins) == ["disabled", "orphan"]
    monkeypatch.setattr(actions, "discover_agent_plugins", lambda *args, **kwargs: plugins)
    with pytest.raises(McpPresetError) as caught:
        actions.mcp_presets_action(
            "remove", {"name": ["multi--left"], "cleanup_only": ["true"]}, config_path=path
        )
    assert caught.value.status == 409
    assert (root / "multi--left").is_dir()


async def test_cleanup_discovery_does_not_borrow_another_instance_credentials(
    tmp_path, monkeypatch
):
    first, second = (tmp_path / name / "config.json" for name in ("first", "second"))
    for path in (first, second):
        config = Config()
        config.agents.defaults.workspace = str(tmp_path / "workspace")
        save_config(config, path)
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", first)
    await MCPOAuthStorage("orphan", "https://old.fixture.test/mcp", config_path=first).set_tokens(
        OAuthToken(access_token="private-fixture-token")
    )
    assert mcp_presets_payload(config_path=first)["cleanup_pending"] == ["orphan"]
    payload = mcp_presets_payload(config_path=second)
    assert payload["cleanup_pending"] == []
    assert "private-fixture-token" not in str(payload)


def test_cleanup_of_orphan_link_preserves_its_outside_target(tmp_path):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    save_config(config, path)
    target = tmp_path / "user-data"
    target.mkdir()
    (target / "keep.txt").write_text("User data")
    root = tmp_path / "state" / "mcp"
    root.mkdir(parents=True)
    try:
        (root / "orphan").symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Directory links are unavailable: {exc}")
    assert mcp_presets_payload(config_path=path)["cleanup_pending"] == ["orphan"]
    result = actions.mcp_presets_action(
        "remove", {"name": ["orphan"], "cleanup_only": ["true"]}, config_path=path
    )
    assert result["cleanup_pending"] == []
    assert (target / "keep.txt").read_text() == "User data"
    assert not (root / "orphan").is_symlink()


def test_orphan_cleanup_preserves_the_exact_directory_name(tmp_path):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    save_config(config, path)
    cwd = tmp_path / "state" / "mcp" / "MixedCase"
    cwd.mkdir(parents=True)
    assert mcp_presets_payload(config_path=path)["cleanup_pending"] == ["MixedCase"]
    response = actions.mcp_presets_action(
        "remove", {"name": ["MixedCase"], "cleanup_only": ["true"]}, config_path=path
    )
    assert response["cleanup_pending"] == []
    assert not cwd.exists()


def test_idempotent_remove_does_not_treat_a_configured_case_alias_as_an_orphan(tmp_path):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    config.tools.mcp_servers["mixedcase"] = MCPServerConfig(command="fixture")
    save_config(config, path)
    with pytest.raises(McpPresetError) as caught:
        actions.mcp_presets_action("remove", {"name": ["MixedCase"]}, config_path=path)
    assert caught.value.status == 409
    assert "mixedcase" in load_config(path).tools.mcp_servers


def test_symlinked_runtime_root_inside_instance_never_adopts_user_data(tmp_path):
    path = tmp_path / "config.json"
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    save_config(config, path)
    target = tmp_path / "user-data" / "orphan"
    target.mkdir(parents=True)
    (target / "keep.txt").write_text("User data")
    root = tmp_path / "state" / "mcp"
    root.parent.mkdir()
    try:
        root.symlink_to(target.parent, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Directory links unavailable: {exc}")
    assert mcp_presets_payload(config_path=path)["cleanup_pending"] == []
    result = actions.mcp_presets_action(
        "remove", {"name": ["orphan"], "cleanup_only": ["true"]}, config_path=path
    )
    assert result["last_action"]["ok"] is False
    assert result["last_action"]["verification_failed"] == ["managed_paths_absent"]
    assert (target / "keep.txt").read_text() == "User data"
    with pytest.raises(McpPresetError, match="runtime directory"):
        actions.mcp_presets_action("enable", {"name": ["playwright"]}, config_path=path)
