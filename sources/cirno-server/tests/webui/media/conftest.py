"""Media transfer tests exercise the real HTTP writer with signed local files."""

from unittest.mock import Mock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from cirno_core.security.workspace_access import default_workspace_scope
from cirno_server.webui.media.http import MediaHTTP
from cirno_server.webui.media_gateway import WebUIMediaServer


@pytest.fixture
async def media_client(tmp_path):
    scope = default_workspace_scope(tmp_path, True)
    gateway = WebUIMediaServer(workspace_path=tmp_path, logger=Mock(), media_dir=lambda _: tmp_path)
    handler = MediaHTTP(gateway, lambda _: scope)
    app = web.Application()
    app.router.add_route("*", "/v0/media/{sig}/{payload}", handler.handle)
    async with TestClient(TestServer(app)) as client:
        yield gateway, client
