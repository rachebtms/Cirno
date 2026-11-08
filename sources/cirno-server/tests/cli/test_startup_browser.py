"""Browser launch readiness and owned development process monitoring."""

import asyncio
import urllib.error
from unittest.mock import MagicMock

import pytest
from cirno_server.cli.startup_browser import http_endpoint_responding
from cirno_server.lifecycle.development import watch_dev_server
from cirno_server.webui.dev import WebUIDevError


async def test_webui_dev_monitor_fails_when_sidecar_exits() -> None:
    dev_server = MagicMock()
    dev_server.ensure_running.side_effect = WebUIDevError(
        "WebUI development server exited unexpectedly (code 23)"
    )

    with pytest.raises(WebUIDevError, match=r"exited unexpectedly \(code 23\)"):
        await watch_dev_server(
            dev_server,
            asyncio.Event(),
            poll_interval_s=0,
        )


async def test_webui_dev_monitor_ignores_an_expected_gateway_shutdown() -> None:
    dev_server = MagicMock()
    shutdown_event = asyncio.Event()
    shutdown_event.set()

    await watch_dev_server(
        dev_server,
        shutdown_event,
        poll_interval_s=0,
    )

    dev_server.ensure_running.assert_not_called()


def test_browser_readiness_accepts_http_auth_response(monkeypatch) -> None:
    def auth_required(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8765/v0/bootstrap",
            401,
            "authentication required",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("urllib.request.urlopen", auth_required)

    assert http_endpoint_responding(
        "http://127.0.0.1:8765/v0/bootstrap"
    ) is True


def test_browser_readiness_rejects_connection_error(monkeypatch) -> None:
    def unavailable(*_args, **_kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", unavailable)

    assert http_endpoint_responding(
        "http://127.0.0.1:8765/v0/bootstrap"
    ) is False
