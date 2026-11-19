"""OAuth storage and settings must not borrow or revoke another instance's tokens."""

import json

import pytest
from cirno_core.agent.tools.mcp_oauth import MCPOAuthStorage
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_core.config.tools import MCPServerConfig
from cirno_server.webui.mcp.actions import mcp_presets_action
from cirno_server.webui.mcp.catalog import mcp_presets_payload
from mcp.shared.auth import OAuthToken


@pytest.fixture
def instances(tmp_path, monkeypatch):
    first, second = (tmp_path / name / "config.json" for name in ("first", "second"))
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    for name in ("company", "xmind"):
        config.tools.mcp_servers[name] = MCPServerConfig(
            type="streamableHttp", auth="oauth", url="https://fixture.test/mcp"
        )
    save_config(config, first)
    save_config(config, second)
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", first)
    return first, second


async def test_storage_keeps_its_owner_when_process_default_changes(instances, monkeypatch):
    from cirno_core.agent.tools.mcp_oauth import _RefreshLease
    from mcp.shared.auth import OAuthMetadata

    first, second = instances
    storage = MCPOAuthStorage("company", "https://fixture.test/mcp")
    await storage.set_tokens(OAuthToken(access_token="first-fixture-token"))
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", second)
    assert (await storage.get_tokens()).access_token == "first-fixture-token"
    await storage.set_tokens(OAuthToken(access_token="updated-first-fixture-token"))
    assert str(storage.refresh_lock().lock_file).startswith(str(first.parent / "state"))
    await storage.set_oauth_metadata(
        OAuthMetadata.model_validate(
            {
                "issuer": "https://auth.fixture.test",
                "authorization_endpoint": "https://auth.fixture.test/authorize",
                "token_endpoint": "https://auth.fixture.test/token",
                "response_types_supported": ["code"],
            }
        )
    )
    await storage.set_tokens(
        OAuthToken(
            access_token="updated-first-fixture-token", refresh_token="first-fixture-refresh"
        )
    )
    lock = storage.refresh_lock()
    await lock.acquire()
    try:
        lease = _RefreshLease(
            lock,
            "updated-first-fixture-token",
            "first-fixture-refresh",
            "https://auth.fixture.test",
        )
        assert await storage.finish_refresh(
            lease, OAuthToken(access_token="rotated-first-fixture-token")
        )
    finally:
        await lock.release()
    assert (await storage.get_tokens()).access_token == "rotated-first-fixture-token"
    assert not (second.parent / "state" / "auth" / "mcp.json").exists()


@pytest.mark.parametrize("action", ["remove", "custom", "import", "import-cursor"])
async def test_removing_explicit_instance_preserves_default_instance_tokens(
    instances, monkeypatch, action
):
    first, second = instances
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", second)
    second_storage = MCPOAuthStorage("company", "https://fixture.test/mcp")
    await second_storage.set_tokens(OAuthToken(access_token="second-fixture-token"))
    monkeypatch.setattr("cirno_core.config.loader._current_config_path", first)
    first_storage = MCPOAuthStorage("company", "https://fixture.test/mcp")
    await first_storage.set_tokens(OAuthToken(access_token="first-fixture-token"))
    if action == "remove":
        mcp_presets_action(action, {"name": ["company"]}, config_path=second)
    else:
        from cirno_server.webui.mcp.configuration import custom_mcp_action

        replacement = {
            "url": "https://replacement.fixture.test/mcp",
            "type": "streamableHttp",
            "auth": "oauth",
        }
        query = {
            "name": ["company"],
            "url": [replacement["url"]],
            "transport": [replacement["type"]],
            "auth": ["oauth"],
        }
        if action != "custom":
            query = {"config": [json.dumps({"mcpServers": {"company": replacement}})]}
        custom_mcp_action(action, query, config_path=second)
    assert (await first_storage.get_tokens()).access_token == "first-fixture-token"
    assert await second_storage.get_tokens() is None
    await second_storage.set_tokens(OAuthToken(access_token="late-second-fixture-token"))
    assert await second_storage.get_tokens() is None
    assert (await first_storage.get_tokens()).access_token == "first-fixture-token"


@pytest.mark.parametrize("name", ["company", "xmind"])
async def test_explicit_catalog_does_not_borrow_default_instance_authorization(instances, name):
    first, second = instances
    await MCPOAuthStorage(name, "https://fixture.test/mcp").set_tokens(
        OAuthToken(access_token="first-fixture-token")
    )
    first_row = next(
        row for row in mcp_presets_payload(config_path=first)["presets"] if row["name"] == name
    )
    second_row = next(
        row for row in mcp_presets_payload(config_path=second)["presets"] if row["name"] == name
    )
    assert first_row["configured"] is True
    assert second_row["status"] == "authorization_required"
    assert second_row["configured"] is False


@pytest.mark.parametrize("phase", ["connect", "reload", "reconnect"])
async def test_provider_keeps_its_oauth_owner_through_its_connection_lifecycle(
    instances, monkeypatch, phase
):
    from types import SimpleNamespace

    from cirno_core.agent.tools.mcp.provider import MCPProvider
    from cirno_core.agent.tools.mcp_oauth import create_mcp_oauth_auth
    from cirno_core.agent.tools.registry import ToolRegistry
    from cirno_core.config.loader import load_config

    first, second = instances
    config = load_config(second)
    config.tools.mcp_servers.pop("xmind")
    save_config(config, second)
    await MCPOAuthStorage("company", "https://fixture.test/mcp", config_path=second).set_tokens(
        OAuthToken(access_token="second-fixture-token")
    )
    observed = []

    class Connection:
        async def aclose(self):
            pass

    async def connect(_servers, _registry, *, network, config_path=None):
        auth = await create_mcp_oauth_auth(
            "company", "https://fixture.test/mcp", config_path=config_path
        )
        observed.append((config_path, (await auth._cirno_storage.get_tokens()).access_token))
        return {"company": Connection()}

    monkeypatch.setattr("cirno_core.agent.tools.mcp.provider.connect_mcp_servers", connect)
    provider = MCPProvider.from_config(load_config(second), ToolRegistry())
    try:
        await provider.connect()
        if phase == "reload":
            config.tools.mcp_servers["company"].tool_timeout += 1
            save_config(config, second)
            await provider.reload()
        elif phase == "reconnect":
            await provider._refresh_terminated_server(
                "company", "mcp_company_fixture", SimpleNamespace()
            )
        assert observed == [(second, "second-fixture-token")] * (1 if phase == "connect" else 2)
        assert not (first.parent / "state" / "auth" / "mcp.json").exists()
    finally:
        await provider.aclose()


async def test_connector_passes_the_owner_to_oauth_creation_before_transport(
    instances, monkeypatch
):
    from cirno_core.agent.tools.mcp.connector import connect_mcp_servers
    from cirno_core.agent.tools.mcp_oauth import MCPAuthorizationRequiredError
    from cirno_core.agent.tools.registry import ToolRegistry

    _, second = instances
    observed = []

    async def create(_name, _url, _handlers, *, config_path=None):
        observed.append(config_path)
        raise MCPAuthorizationRequiredError("Fixture stops before network transport")

    monkeypatch.setattr("cirno_core.agent.tools.mcp_oauth.create_mcp_oauth_auth", create)
    monkeypatch.setattr(
        "cirno_core.agent.tools.mcp.connector.validate_url_target", lambda _: (True, "")
    )
    result = await connect_mcp_servers(
        {
            "company": MCPServerConfig(
                type="streamableHttp", auth="oauth", url="https://fixture.test/mcp"
            )
        },
        ToolRegistry(),
        config_path=second,
    )
    assert result == {}
    assert observed == [second]


async def test_browser_authorization_route_uses_its_settings_instance(instances, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from cirno_core.agent.tools.mcp_oauth import create_mcp_oauth_auth
    from cirno_core.bus.queue import MessageBus
    from cirno_server.webui.settings.routes import WebUISettingsRouter
    from cirno_server.webui.settings.services import WebUISettingsServices

    first, second = instances
    observed = []

    async def connect(_servers, _registry, *, oauth_handlers, network, config_path=None):
        auth = await create_mcp_oauth_auth(
            "company",
            "https://fixture.test/mcp",
            oauth_handlers["company"],
            config_path=config_path,
        )
        await auth._cirno_storage.set_tokens(OAuthToken(access_token="second-fixture-token"))
        observed.append(config_path)
        return {}

    monkeypatch.setattr("cirno_server.webui.mcp.oauth_api.connect_mcp_servers", connect)
    router = WebUISettingsRouter(
        settings=WebUISettingsServices.create(second),
        bus=MessageBus(),
        logger=MagicMock(),
        check_api_token=lambda _: True,
        parse_query=lambda _: {},
        json_response=lambda value: value,
        error_response=lambda status, message: {"status": status, "error": message},
        mcp_oauth_redirect_uri=lambda _: "https://fixture.test/v0/mcp/oauth/callback",
    )
    path = "/v0/settings/mcp-oauth/start"
    request = SimpleNamespace(
        path=path,
        _cirno_webui_mutation_request=True,
        _cirno_webui_mutation_payload={"name": "company"},
    )
    try:
        payload = await router.dispatch(None, request, path)
        assert payload["name"] == "company"
        assert observed == [second]
        assert (
            await MCPOAuthStorage(
                "company", "https://fixture.test/mcp", config_path=second
            ).get_tokens()
        ).access_token == "second-fixture-token"
        assert not (first.parent / "state" / "auth" / "mcp.json").exists()
    finally:
        await router.close()


async def test_inspection_uses_the_requested_instance_authorization(instances, monkeypatch):
    from cirno_core.agent.tools.mcp_oauth import create_mcp_oauth_auth
    from cirno_server.webui.mcp.inspection import mcp_presets_test_action

    first, second = instances
    await MCPOAuthStorage("company", "https://fixture.test/mcp", config_path=second).set_tokens(
        OAuthToken(access_token="second-fixture-token")
    )
    observed = []

    class Connection:
        async def aclose(self):
            pass

    async def connect(_servers, _registry, *, network, config_path=None):
        auth = await create_mcp_oauth_auth(
            "company", "https://fixture.test/mcp", config_path=config_path
        )
        observed.append((config_path, (await auth._cirno_storage.get_tokens()).access_token))
        return {"company": Connection()}

    monkeypatch.setattr("cirno_core.agent.tools.mcp.connector.connect_mcp_servers", connect)
    payload = await mcp_presets_test_action({"name": ["company"]}, config_path=second)
    assert payload["last_action"]["ok"] is True
    assert observed == [(second, "second-fixture-token")]
    assert not (first.parent / "state" / "auth" / "mcp.json").exists()
