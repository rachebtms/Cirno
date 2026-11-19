"""Invalid callbacks cannot consume an otherwise live sign-in flow."""

import io
import queue
import threading
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlencode

import httpx
import pytest
from cirno_core.providers import xai_oauth


def callback_handler(monkeypatch):
    handlers = []
    server = SimpleNamespace()
    def server_factory(_address, handler):
        handlers.append(handler)
        return server
    monkeypatch.setattr(xai_oauth, "ThreadingHTTPServer", server_factory)
    results = queue.Queue(maxsize=1)
    assert xai_oauth._make_callback_server("expected-state", results) is server
    return handlers[0], results


def invoke(handler_class, params):
    handler = handler_class.__new__(handler_class)
    handler.path = "/callback?" + urlencode(params)
    handler.headers = {}
    handler.wfile = io.BytesIO()
    handler.send_error = Mock()
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    handler.do_GET()
    return handler


@pytest.mark.parametrize("params", [
    {"code": "foreign-code", "state": "wrong-state"},
    {"code": "foreign-code"},
    {"error": "access_denied", "state": "wrong-state"},
    {"error": "access_denied"},
    {"code": "foreign-code", "state": "错误状态"},
])
def test_unrelated_callback_does_not_displace_real_authorization(monkeypatch, params):
    handler, results = callback_handler(monkeypatch)
    response = invoke(handler, params)
    assert results.empty(), "unrelated callback consumed the pending authorization result"
    assert response.send_error.call_args.args[0] == HTTPStatus.BAD_REQUEST
    response = invoke(handler, {"code": "real-code", "state": "expected-state"})
    response.send_response.assert_called_once_with(HTTPStatus.OK)
    assert results.get_nowait() == xai_oauth._CallbackResult(code="real-code", state="expected-state")


def test_matching_authorization_denial_is_still_delivered(monkeypatch):
    handler, results = callback_handler(monkeypatch)
    invoke(handler, {"error": "access_denied", "state": "expected-state"})
    assert results.get_nowait().error == "access_denied"


@pytest.mark.parametrize("access", ["", None, 42])
def test_unusable_access_token_is_rejected_before_credential_commit(access):
    with pytest.raises(xai_oauth.XAIOAuthError, match="no access token"):
        xai_oauth._token_payload(httpx.Response(200, json={"access_token": access}))


def test_nonempty_access_token_stays_opaque():
    payload = {"access_token": "opaque-fixture", "refresh_token": "rotated-fixture"}
    assert xai_oauth._token_payload(httpx.Response(200, json=payload)) == payload


def pending_flow():
    flow = xai_oauth.XAIOAuthLoginFlow.__new__(xai_oauth.XAIOAuthLoginFlow)
    flow._lock = threading.Lock()
    flow._token = None
    flow._error = None
    flow._state = "expected-state"
    flow.redirect_uri = "http://127.0.0.1:54321/callback"
    flow._finish = Mock(return_value=SimpleNamespace(access="fake-access"))
    return flow


@pytest.mark.parametrize("response,expected", [
    ("opaque-code", xai_oauth._CallbackResult(code="opaque-code")),
    ("http://127.0.0.1:54321/callback?code=real-code&state=expected-state", xai_oauth._CallbackResult(code="real-code", state="expected-state")),
    ("http://127.0.0.1:54321/callback?error=access_denied&state=expected-state", xai_oauth._CallbackResult(state="expected-state", error="access_denied")),
])
def test_pasted_code_or_callback_is_converted_before_exchange(response, expected):
    flow = pending_flow()
    assert flow.complete(response).access == "fake-access"
    flow._finish.assert_called_once_with(expected)


@pytest.mark.parametrize("response", [
    "",
    "http://127.0.0.1:54321/callback?code=foreign&state=wrong",
    "http://127.0.0.1:54321/callback?code=foreign&state=%E9%94%99%E8%AF%AF",
    "http://127.0.0.1:54321/callback?code=foreign",
    "https://foreign.test/callback?code=foreign&state=expected-state",
    "http://127.0.0.1:12345/callback?code=foreign&state=expected-state",
    "http://127.0.0.1:54321/callback?state=expected-state",
    "http://[invalid/callback?code=foreign",
])
def test_invalid_pasted_input_cannot_start_exchange_or_consume_flow(response):
    flow = pending_flow()
    with pytest.raises(xai_oauth.XAIOAuthError):
        flow.complete(response)
    flow._finish.assert_not_called()
    assert flow._error is None
