"""Exercise browser registration on the real combined HTTP/WebSocket listener."""

import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import httpx
import pytest
import websockets
from cirno_core.bus.queue import MessageBus
from cirno_server.channels.websocket.config import WebSocketConfig
from cirno_server.channels.websocket.runtime import WebSocketChannel
from cirno_server.webui.auth.store import AccountError, AccountStore
from cirno_server.webui.services import build_server_services

PASSWORD = "CirnoTest!"


@asynccontextmanager
async def listener(home, sessions=None):
    config = WebSocketConfig(host="0.0.0.0", port=0, browser_setup=True)
    bus = MessageBus()
    gateway = build_server_services(
        config=config, bus=bus, session_manager=sessions, static_dist_path=None,
        workspace_path=home / "workspace", config_path=home / "config.json",
        default_restrict_to_workspace=False, runtime_model_name=None,

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
            assert (await browser.get("/v0/auth/status")).json()["registration_required"]
            assert (await browser.get("/v0/bootstrap")).status_code == 428
            assert (await browser.get("/v0/settings")).status_code == 401
            with pytest.raises(websockets.exceptions.InvalidStatus):
                async with websockets.connect(url.replace("http:", "ws:")):
                    pytest.fail("An unregistered instance accepted a socket")
            response = await browser.post("/v0/auth/register", json={"username": "owner", "password": PASSWORD})
            assert response.status_code == 201, response.text
            assert "HttpOnly" in response.headers["set-cookie"]
            assert "SameSite=Strict" in response.headers["set-cookie"]
            assert PASSWORD not in response.text
            assert not (await browser.get("/v0/auth/status")).json()["registration_required"]
            response = await browser.post("/v0/auth/register", json={"username": "intruder", "password": PASSWORD})
            assert response.status_code == 409
            boot = (await browser.get("/v0/bootstrap")).json()
            assert boot["browser_auth"] and boot["onboarding_required"]
            async with websockets.connect(url.replace("http:", "ws:") + "/v0/ws?token=" + boot["token"]) as socket:
                ready = json.loads(await socket.recv())
                assert ready["event"] == "ready"
            assert (await browser.post("/v0/auth/complete", json={})).status_code == 200
            assert not (await browser.get("/v0/bootstrap")).json()["onboarding_required"]
            cookie = browser.cookies.get("cirno_session")
            assert (await browser.post("/v0/auth/logout", json={})).status_code == 200
            assert (await browser.get("/v0/bootstrap")).status_code == 401
            assert (await browser.get("/v0/bootstrap", headers={"Cookie": f"cirno_session={cookie}"})).status_code == 401
            assert (await browser.post("/v0/auth/login", json={"username": "owner", "password": "wrong"})).status_code == 401
            assert (await browser.post("/v0/auth/login", json={"username": "owner", "password": PASSWORD})).status_code == 200
            cookie = browser.cookies.get("cirno_session")
    # Browser sessions and setup completion survive a process restart.
    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as browser:
            assert (await browser.get("/v0/bootstrap")).status_code == 401
            boot = await browser.get("/v0/bootstrap", headers={"Cookie": f"cirno_session={cookie}"})
            assert boot.status_code == 200
            assert not boot.json()["onboarding_required"]
            assert (await browser.post("/v0/auth/register", json={"username": "new", "password": PASSWORD})).status_code == 409


@pytest.mark.asyncio
async def test_registration_rejects_cross_origin_and_invalid_bodies(tmp_path):
    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as browser:
            values = {"username": "owner", "password": PASSWORD}
            assert (await browser.post("/v0/auth/register", json=values, headers={"Origin": "https://other.example"})).status_code == 403
            assert (await browser.post("/v0/auth/register", data=values)).status_code == 415
            assert (await browser.post("/v0/auth/register", content='{"password":', headers={"Content-Type": "application/json"})).status_code == 400
            assert (await browser.post("/v0/auth/register", json={"username": "owner", "password": "short"})).status_code == 400
            assert (await browser.post("/v0/auth/register", json={"username": "owner", "password": "x" * 9000})).status_code == 413
            assert (await browser.get("/v0/auth/register")).status_code == 405
            assert (await browser.post("/v0/auth/complete", json={})).status_code == 401
            assert (await browser.get("/v0/auth/status")).json()["registration_required"]
            assert (await browser.post("/v0/auth/register", json=values, headers={"Origin": url})).status_code == 201


@pytest.mark.asyncio
async def test_proxy_chunked_json_is_supported_and_still_bounded(tmp_path):
    async def chunks(value):
        yield value[:10]
        yield value[10:]

    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as browser:
            headers = {"Content-Type": "application/json"}
            large = json.dumps({"username": "owner", "password": "x" * 9000}).encode()
            assert (await browser.post("/v0/auth/register", content=chunks(large), headers=headers)).status_code == 413
            valid = json.dumps({"username": "owner", "password": PASSWORD}).encode()
            assert (await browser.post("/v0/auth/register", content=chunks(valid), headers=headers)).status_code == 201


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
    AccountStore(tmp_path / "state" / "webui-auth.sqlite3").register("owner", PASSWORD)
    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as browser:
            for _ in range(10):
                assert (await browser.post("/v0/auth/login", json={"username": "owner", "password": "wrong"})).status_code == 401
            assert (await browser.post("/v0/auth/login", json={"username": "owner", "password": "wrong"})).status_code == 429


@pytest.mark.asyncio
async def test_change_password_checks_credentials_revokes_other_sessions_and_sockets(tmp_path):
    new_password = "NewCirnoPassword!"
    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as owner, httpx.AsyncClient(base_url=url) as other:
            assert (await owner.post("/v0/auth/register", json={"username": "owner", "password": PASSWORD})).status_code == 201
            assert (await other.post("/v0/auth/login", json={"username": "owner", "password": PASSWORD})).status_code == 200
            assert (await owner.get("/v0/auth/status")).json()["username"] == "owner"
            boot = (await other.get("/v0/bootstrap")).json()
            async with websockets.connect(url.replace("http:", "ws:") + "/v0/ws?token=" + boot["token"]) as socket:
                await socket.recv()
                endpoint = "/v0/auth/change-password"
                for payload, status, error in [
                    ({"current_password": "wrong", "new_password": new_password}, 403, "incorrect_password"),
                    ({"current_password": PASSWORD, "new_password": "short"}, 400, "invalid_password"),
                ]:
                    response = await owner.post(endpoint, json=payload)
                    assert response.status_code == status
                    assert response.json()["error"] == error
                assert (await other.get("/v0/auth/status")).json()["authenticated"]
                response = await owner.post(endpoint, json={"current_password": PASSWORD, "new_password": new_password}, headers={"Origin": "https://untrusted.example"})
                assert response.status_code == 403
                response = await owner.post(endpoint, json={"current_password": PASSWORD, "new_password": new_password})
                assert response.status_code == 200, response.text
                await asyncio.wait_for(socket.wait_closed(), 5)
                assert socket.close_code == 4001
            assert (await owner.get("/v0/auth/status")).json()["authenticated"]
            assert not (await other.get("/v0/auth/status")).json()["authenticated"]
            assert (await other.get("/v0/settings", headers={"Authorization": "Bearer " + boot["api_token"]})).status_code == 401
            assert (await other.post(endpoint, json={"current_password": PASSWORD, "new_password": new_password})).status_code == 401
            assert (await other.post("/v0/auth/login", json={"username": "owner", "password": PASSWORD})).status_code == 401
            assert (await other.post("/v0/auth/login", json={"username": "owner", "password": new_password})).status_code == 200
            assert (await owner.get("/v0/bootstrap")).status_code == 200
    # Password changes survive restart and never recreate an owner in the old location.
    assert (tmp_path / "state" / "webui-auth.sqlite3").is_file()
    assert not (tmp_path / "webui-auth.sqlite3").exists()
    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as browser:
            assert (await browser.post("/v0/auth/login", json={"username": "owner", "password": new_password})).status_code == 200


@pytest.mark.asyncio
async def test_logout_revokes_own_live_and_unused_capabilities_but_preserves_other_login(tmp_path):
    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as owner, httpx.AsyncClient(base_url=url) as other:
            await owner.post("/v0/auth/register", json={"username": "owner", "password": PASSWORD})
            await other.post("/v0/auth/login", json={"username": "owner", "password": PASSWORD})
            boot = (await owner.get("/v0/bootstrap")).json()
            unused = (await owner.get("/v0/bootstrap")).json()
            other_boot = (await other.get("/v0/bootstrap")).json()
            ws_url = url.replace("http:", "ws:") + "/v0/ws?token="
            async with websockets.connect(ws_url + boot["token"]) as socket, websockets.connect(ws_url + other_boot["token"]) as other_socket:
                await socket.recv()
                await other_socket.recv()
                assert (await owner.post("/v0/auth/logout", json={})).status_code == 200
                await asyncio.wait_for(socket.wait_closed(), 5)
                assert socket.close_code == 4001
                assert (await owner.get("/v0/settings", headers={"Authorization": "Bearer " + boot["api_token"]})).status_code == 401
                with pytest.raises(websockets.exceptions.InvalidStatus):
                    async with websockets.connect(ws_url + unused["token"]):
                        pytest.fail("A logged-out handshake token was accepted")
                assert (await other.get("/v0/settings", headers={"Authorization": "Bearer " + other_boot["api_token"]})).status_code == 200
                await other_socket.send(json.dumps({"type": "webui_request", "request_id": "still-open", "action": "connection.check", "payload": {}}))
                reply = json.loads(await asyncio.wait_for(other_socket.recv(), 5))
                assert reply["ok"]


@pytest.mark.asyncio
async def test_router_name_is_selected_once_and_login_cannot_change_it(tmp_path):
    async with listener(tmp_path) as url:
        async with httpx.AsyncClient(base_url=url) as browser:
            response = await browser.post("/v0/auth/register", json={"username": "owner", "password": PASSWORD, "router_handle": "@Snow_9"})
            assert response.status_code == 201
            assert (await browser.get("/v0/auth/status")).json()["router_handle"] == "snow_9"
            assert (await browser.post("/v0/auth/register", json={"username": "owner", "password": PASSWORD, "router_handle": "other"})).status_code == 409
            await browser.post("/v0/auth/logout", json={})
            assert (await browser.post("/v0/auth/login", json={"username": "owner", "password": PASSWORD, "router_handle": "other"})).status_code == 200
            assert (await browser.get("/v0/auth/status")).json()["router_handle"] == "snow_9"
    assert AccountStore(tmp_path / "state/webui-auth.sqlite3").router_handle() == "snow_9"


@pytest.mark.parametrize("name", ["a", "a b", "_name", "9name", "a" * 33, None])
def test_invalid_router_name_does_not_partially_register_the_owner(tmp_path, name):
    store = AccountStore(tmp_path / "auth.sqlite3")
    with pytest.raises(AccountError, match="invalid_router_handle"):
        store.register("owner", PASSWORD, name)
    assert store.owner() is None


@pytest.mark.asyncio
async def test_registration_initializes_the_real_router_handle_for_tools(tmp_path):
    from cirno_core.session.manager import SessionManager
    from cirno_core.session.keys import ROUTER_SESSION_KEY
    from cirno_core.session.session_handles import SessionHandleResolver
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "state/sessions")
    try:
        async with listener(tmp_path, sessions) as url:
            async with httpx.AsyncClient(base_url=url) as browser:
                assert (await browser.post("/v0/auth/register", json={"username": "owner", "password": PASSWORD, "router_handle": "snow_9"})).status_code == 201
                router = await sessions.state.read_header(ROUTER_SESSION_KEY)
                assert router.metadata["session_handle"] == "snow_9"
                assert router.metadata["role"] == "router"
                assert (await SessionHandleResolver(sessions).aresolve("@snow_9")).session_key == ROUTER_SESSION_KEY
                assert await SessionHandleResolver(sessions).aresolve("@cirno") is None
    finally:
        await sessions.state.aclose()


@pytest.mark.asyncio
async def test_owner_can_rename_router_without_changing_id_and_collision_is_visible(tmp_path):
    from cirno_core.session.manager import SessionManager
    from cirno_core.session.keys import ROUTER_SESSION_KEY
    from cirno_core.session.session_handles import SessionHandleResolver
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "state/sessions")
    worker = sessions.get_or_create("websocket:worker")
    worker.metadata["session_handle"] = "taken_name"
    sessions.save(worker)
    try:
        async with listener(tmp_path, sessions) as url:
            async with httpx.AsyncClient(base_url=url) as browser:
                assert (await browser.post("/v0/auth/change-router-name", json={"router_handle": "snow_9"})).status_code == 401
                rejected = await browser.post("/v0/auth/register", json={"username": "owner", "password": PASSWORD, "router_handle": "taken_name"})
                assert rejected.status_code == 409 and rejected.json()["error"] == "router_handle_taken"
                assert (await browser.get("/v0/auth/status")).json()["registration_required"]
                assert (await browser.post("/v0/auth/register", json={"username": "owner", "password": PASSWORD})).status_code == 201
                old = (await browser.get("/v0/auth/status")).json()
                conflict = await browser.post("/v0/auth/change-router-name", json={"router_handle": "taken_name"})
                assert conflict.status_code == 409 and conflict.json()["error"] == "router_handle_taken"
                assert (await browser.get("/v0/auth/status")).json()["router_handle"] == "cirno"
                changed = await browser.post("/v0/auth/change-router-name", json={"router_handle": "@Snow_9"})
                assert changed.status_code == 200
                assert changed.json() == {"id": old["router_id"], "name": "snow_9"}
                await browser.post("/v0/auth/logout", json={})
                assert (await browser.post("/v0/auth/login", json={"username": "owner", "password": PASSWORD})).status_code == 200
                current = (await browser.get("/v0/auth/status")).json()
                assert (current["router_id"], current["router_handle"]) == (old["router_id"], "snow_9")
                assert (await SessionHandleResolver(sessions).aresolve(old["router_id"])).session_key == ROUTER_SESSION_KEY
    finally:
        await sessions.state.aclose()
