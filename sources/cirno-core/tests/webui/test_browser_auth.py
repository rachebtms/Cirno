"""Exercise browser registration on the real combined HTTP/WebSocket listener."""

import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import httpx
import pytest
import websockets

from cirno.bus.queue import MessageBus
from cirno.channels.websocket.runtime import WebSocketChannel, WebSocketConfig
from cirno.webui.auth.store import AccountError, AccountStore
from cirno.webui.gateway_services import build_gateway_services

PASSWORD = "CirnoTest!"


@asynccontextmanager
async def listener(home):
    config = WebSocketConfig(host="0.0.0.0", port=0, browser_setup=True)
    bus = MessageBus()
    gateway = build_gateway_services(
        config=config, bus=bus, session_manager=None, static_dist_path=None,
        workspace_path=home / "workspace", config_path=home / "config.json",
        default_restrict_to_workspace=False, runtime_model_name=None,
        runtime_surface="browser", runtime_capabilities_overrides=None,
    )
    channel = WebSocketChannel(config.model_dump(by_alias=True), bus, gateway=gateway)
    task = asyncio.create_task(channel.start())
    try:
        async with asyncio.timeout(5):
            while channel._server is None or not channel._server.sockets:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{channel._server.sockets[0].getsockname()[1]}"
    finally:
        await channel.stop()
        await task


@pytest.mark.asyncio
async def test_register_login_resume_and_logout_over_real_listener(tmp_path):
    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as browser:
            assert (await browser.get("/api/auth/status")).json()["registration_required"]
            assert (await browser.get("/webui/bootstrap")).status_code == 428
            assert (await browser.get("/api/settings")).status_code == 401
            with pytest.raises(websockets.exceptions.InvalidStatus):
                async with websockets.connect(url.replace("http:", "ws:")):
                    pytest.fail("An unregistered instance accepted a socket")
            response = await browser.post("/api/auth/register", json={"username": "owner", "password": PASSWORD})
            assert response.status_code == 201, response.text
            assert "HttpOnly" in response.headers["set-cookie"]
            assert "SameSite=Strict" in response.headers["set-cookie"]
            assert PASSWORD not in response.text
            assert not (await browser.get("/api/auth/status")).json()["registration_required"]
            response = await browser.post("/api/auth/register", json={"username": "intruder", "password": PASSWORD})
            assert response.status_code == 409
            boot = (await browser.get("/webui/bootstrap")).json()
            assert boot["browser_auth"] and boot["onboarding_required"]
            async with websockets.connect(url.replace("http:", "ws:") + "/?token=" + boot["token"]) as socket:
                ready = json.loads(await socket.recv())
                assert ready["event"] == "ready"
            assert (await browser.post("/api/auth/complete", json={})).status_code == 200
            assert not (await browser.get("/webui/bootstrap")).json()["onboarding_required"]
            cookie = browser.cookies.get("cirno_session")
            assert (await browser.post("/api/auth/logout", json={})).status_code == 200
            assert (await browser.get("/webui/bootstrap")).status_code == 401
            assert (await browser.get("/webui/bootstrap", headers={"Cookie": f"cirno_session={cookie}"})).status_code == 401
            assert (await browser.post("/api/auth/login", json={"username": "owner", "password": "wrong"})).status_code == 401
            assert (await browser.post("/api/auth/login", json={"username": "owner", "password": PASSWORD})).status_code == 200
            cookie = browser.cookies.get("cirno_session")
    # Browser sessions and setup completion survive a process restart.
    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as browser:
            assert (await browser.get("/webui/bootstrap")).status_code == 401
            boot = await browser.get("/webui/bootstrap", headers={"Cookie": f"cirno_session={cookie}"})
            assert boot.status_code == 200
            assert not boot.json()["onboarding_required"]
            assert (await browser.post("/api/auth/register", json={"username": "new", "password": PASSWORD})).status_code == 409


@pytest.mark.asyncio
async def test_registration_rejects_cross_origin_and_invalid_bodies(tmp_path):
    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as browser:
            values = {"username": "owner", "password": PASSWORD}
            assert (await browser.post("/api/auth/register", json=values, headers={"Origin": "https://other.example"})).status_code == 403
            assert (await browser.post("/api/auth/register", data=values)).status_code == 415
            assert (await browser.post("/api/auth/register", content='{"password":', headers={"Content-Type": "application/json"})).status_code == 400
            assert (await browser.post("/api/auth/register", json={"username": "owner", "password": "short"})).status_code == 400
            assert (await browser.post("/api/auth/register", json={"username": "owner", "password": "x" * 9000})).status_code == 413
            assert (await browser.get("/api/auth/register")).status_code == 405
            assert (await browser.post("/api/auth/complete", json={})).status_code == 401
            assert (await browser.get("/api/auth/status")).json()["registration_required"]
            assert (await browser.post("/api/auth/register", json=values, headers={"Origin": url})).status_code == 201


@pytest.mark.asyncio
async def test_proxy_chunked_json_is_supported_and_still_bounded(tmp_path):
    async def chunks(value):
        yield value[:10]
        yield value[10:]

    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as browser:
            headers = {"Content-Type": "application/json"}
            large = json.dumps({"username": "owner", "password": "x" * 9000}).encode()
            assert (await browser.post("/api/auth/register", content=chunks(large), headers=headers)).status_code == 413
            valid = json.dumps({"username": "owner", "password": PASSWORD}).encode()
            assert (await browser.post("/api/auth/register", content=chunks(valid), headers=headers)).status_code == 201


def test_only_one_owner_can_win_concurrent_registration(tmp_path):
    path = tmp_path / "webui-auth.sqlite3"

    def register(username):
        try:
            AccountStore(path).register(username, PASSWORD)
            return "created"
        except AccountError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(register, ["first", "second"]))
    assert sorted(results) == ["created", "registration_closed"]
    assert PASSWORD.encode() not in path.read_bytes()
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT count(*) FROM owner").fetchone()[0] == 1


@pytest.mark.parametrize("password", ["Short!A", "lowercase!", "UPPERCASEONLY", "Uppercase ", "Password中文", "PasswordA\u200b"])
def test_registration_requires_ten_characters_uppercase_and_symbol(tmp_path, password):
    store = AccountStore(tmp_path / "auth.sqlite3")
    with pytest.raises(AccountError, match="invalid_password"):
        store.register("owner", password)
    assert store.owner() is None


@pytest.mark.parametrize("password", ["ABCDEFGHI!", "A" * 1100 + "!", "Abcdefghi💠", "Ébcdefghi!"])
def test_passwords_have_no_additional_character_or_maximum_length_rules(tmp_path, password):
    store = AccountStore(tmp_path / "auth.sqlite3")
    store.register("owner", password)
    assert store.authenticated(store.login("owner", password))


@pytest.mark.asyncio
async def test_failed_login_is_rate_limited(tmp_path):
    AccountStore(tmp_path / "webui-auth.sqlite3").register("owner", PASSWORD)
    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as browser:
            for _ in range(10):
                assert (await browser.post("/api/auth/login", json={"username": "owner", "password": "wrong"})).status_code == 401
            assert (await browser.post("/api/auth/login", json={"username": "owner", "password": "wrong"})).status_code == 429
