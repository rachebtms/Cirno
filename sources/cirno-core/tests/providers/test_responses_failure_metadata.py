"""Responses failure events survive transport parsing and provider retry routing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.providers.azure_openai_provider import AzureOpenAIProvider
from cirno_core.providers.chat_completions.errors import error_response
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.errors import is_transient_response, public_error_kind
from cirno_core.providers.model_api import ModelAPICapabilities
from cirno_core.providers.openai_codex_provider import _codex_error_response
from cirno_core.providers.openai_compat_provider import OpenAICompatProvider
from cirno_core.providers.openai_responses import ResponsesBackend, consume_sse_with_reasoning
from cirno_core.providers.openai_responses.state import is_compaction_compatibility_error
from cirno_core.providers.xai_grok_provider import _xai_error_response

PRIVATE = "PRIVATE INPUT fixture-api-token"


class Stream:
    def __init__(self, *events):
        self.events = events
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        self.closed = True

    async def close(self):
        self.closed = True

    async def __aiter__(self):
        for event in self.events:
            if isinstance(event, Exception):
                raise event
            yield event


def failure(code="server_error", **fields):
    return {
        "type": "response.failed",
        "response": {
            "status": "failed",
            "error": {"code": code, "message": PRIVATE},
        },
        **fields,
    }


def provider_with(*results):
    create = AsyncMock(side_effect=results)
    provider = OpenAICompatProvider(
        api_key="fixture",
        default_model="fixture-model",
        model_api=ModelAPICapabilities(("responses",), "responses"),
    )
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create), close=AsyncMock())
    return provider, create


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize(
    "code, retry, category",
    [
        ("server_error", True, "server"),
        ("rate_limit_exceeded", True, "rate_limit"),
        ("insufficient_quota", False, "billing"),
    ],
)
async def test_native_failure_keeps_machine_error_for_stream_and_complete(
    streaming, code, retry, category
):
    event = failure(code)
    stream = Stream(event)
    provider, create = provider_with(stream if streaming else event["response"])
    call = provider.chat_stream if streaming else provider.chat
    result = await call([{"role": "user", "content": "fixture"}])
    assert result.finish_reason == "error"
    assert result.error_code == code
    assert result.error_should_retry is retry
    assert is_transient_response(result) is retry
    assert public_error_kind(result) == category
    assert PRIVATE not in result.content
    assert not result.tool_calls
    create.assert_awaited_once()
    if streaming:
        assert stream.closed


@pytest.mark.parametrize(
    "handler",
    [error_response, AzureOpenAIProvider._handle_error, _codex_error_response, _xai_error_response],
)
async def test_owned_adapters_keep_failed_stream_status_retry_delay_and_safe_error(handler):
    async def events():
        yield failure("rate_limit_exceeded", status=429, headers={"Retry-After": "3"})

    with pytest.raises(RuntimeError) as caught:
        await ResponsesBackend.consume(events())
    result = handler(caught.value)
    assert result.error_status_code == 429
    assert result.error_code == "rate_limit_exceeded"
    assert result.error_should_retry is True
    assert result.error_retry_after_s == 3
    assert public_error_kind(result) == "rate_limit"
    assert PRIVATE not in result.content


async def test_failed_stream_retries_serially_and_closes_each_stream(monkeypatch):
    failed = Stream(failure("rate_limit_exceeded", headers={"Retry-After": "3"}))
    success = Stream(
        {"type": "response.output_text.delta", "delta": "verified"},
        {"type": "response.completed", "response": {"status": "completed", "output": []}},
    )
    provider, create = provider_with(failed, success)
    provider.retry_policy.delays = (0.1,)
    waits = []

    async def wait(_self, delay, **options):
        assert failed.closed
        assert create.await_count == 1
        waits.append((delay, options["error_kind"]))

    monkeypatch.setattr("cirno_core.providers.retry.ProviderRetryExecutor.wait", wait)
    result = await provider.chat_stream_with_retry([{"role": "user", "content": "fixture"}])
    assert result.content == "verified"
    assert result.finish_reason == "stop"
    assert waits == [(4.0, "rate_limit")]
    assert create.await_count == 2
    assert success.closed


@pytest.mark.parametrize("activity", ["none", "content", "reasoning", "tool"])
async def test_optional_api_fallback_is_allowed_only_before_response_output(activity):
    events = {
        "none": [],
        "content": [{"type": "response.output_text.delta", "delta": "partial"}],
        "reasoning": [{"type": "response.reasoning_text.delta", "delta": "thinking"}],
        "tool": [
            {
                "type": "response.output_item.added",
                "item": {
                    "type": "function_call",
                    "call_id": "fixture",
                    "name": "inspect",
                    "arguments": "",
                },
            }
        ],
    }
    failed = Stream(*events[activity], failure("unsupported", status=400))
    provider, _create = provider_with(failed)
    provider._preset_model_api = ModelAPICapabilities(
        ("responses", "chat_completions"), "responses"
    )
    fallback = Stream(
        {
            "choices": [{"delta": {"content": "fallback"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    )
    chat = AsyncMock(return_value=fallback)
    provider._client.chat = SimpleNamespace(completions=SimpleNamespace(create=chat))
    result = await provider.chat_stream([{"role": "user", "content": "fixture"}])
    assert failed.closed
    if activity == "none":
        assert result.content == "fallback"
        chat.assert_awaited_once()
        assert fallback.closed
    else:
        assert result.finish_reason == "error"
        assert result.error_code == "unsupported"
        chat.assert_not_awaited()


@pytest.mark.parametrize("streaming", [False, True])
async def test_failed_response_keeps_usage_and_never_attaches_continuation_state(streaming):
    event = failure()
    event["response"]["usage"] = {"input_tokens": 11, "output_tokens": 3}
    event["response"]["output"] = [
        {"type": "function_call", "name": "inspect", "call_id": "fixture", "arguments": "{}"}
    ]
    provider, _create = provider_with(Stream(event) if streaming else event["response"])
    result = await (provider.chat_stream if streaming else provider.chat)(
        [{"role": "user", "content": "fixture"}]
    )
    assert result.usage is not None
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 3
    assert result.provider_state is None
    assert not result.tool_calls


@pytest.mark.parametrize(
    "kind, category", [("rate_limit", "rate_limit"), ("server_error", "server")]
)
def test_public_error_category_keeps_known_error_kind_without_http_status(kind, category):
    assert (
        public_error_kind(
            LLMResponse(content="safe failure", finish_reason="error", error_kind=kind)
        )
        == category
    )


@pytest.mark.parametrize("legacy", [False, True])
async def test_sse_error_shape_keeps_retry_hints_without_echoing_upstream_text(legacy):
    import json

    event = (
        {"type": "error", "error": "rate limit, try again in 2 seconds: " + PRIVATE}
        if legacy
        else {
            "type": "error",
            "code": "rate_limit_exceeded",
            "message": PRIVATE,
            "headers": {"Retry-After": "2"},
        }
    )

    class Body:
        async def aiter_lines(self):
            yield "data: " + json.dumps(event)
            yield ""

    with pytest.raises(RuntimeError) as caught:
        await consume_sse_with_reasoning(Body())
    response = error_response(caught.value)
    assert response.error_should_retry is True
    assert response.error_retry_after_s == 2
    assert PRIVATE not in response.content
    assert response.error_type != "error"


async def test_compaction_rejection_is_classified_without_storing_its_message():
    async def events():
        yield {
            "type": "error",
            "status": 400,
            "error": {
                "code": "invalid_request_error",
                "param": "context_management",
                "message": "unknown parameter context_management; " + PRIVATE,
            },
        }

    with pytest.raises(RuntimeError) as caught:
        await ResponsesBackend.consume(events())
    assert is_compaction_compatibility_error(caught.value)
    assert PRIVATE not in str(caught.value)


@pytest.mark.parametrize(
    "code, category", [("rate_limit_exceeded", "rate_limit"), ("server_error", "server")]
)
async def test_failure_category_reaches_runner_result_without_executing_partial_tools(
    code, category
):
    from cirno_core.agent.hook import AgentHook
    from cirno_core.agent.runner.engine import AgentRunner

    from sources.development.testing.runtime import make_run_spec

    class Hook(AgentHook):
        def wants_streaming(self):
            return True

    provider, create = provider_with(Stream(failure(code)))
    provider.retry_policy.delays = ()
    tools = Mock(execute=AsyncMock())
    tools.get_definitions.return_value = []
    result = await AgentRunner().run(
        make_run_spec(
            provider,
            model="fixture-model",
            tools=tools,
            hook=Hook(),
            max_iterations=1,
            max_tool_result_chars=2000,
            initial_messages=[{"role": "user", "content": "fixture"}],
        )
    )
    assert result.stop_reason == "error"
    assert result.failure_error_kind == category
    assert PRIVATE not in str(result.messages)
    create.assert_awaited_once()
    tools.execute.assert_not_awaited()


@pytest.mark.parametrize(
    "code, retry, category",
    [("rate_limit_exceeded", True, "rate_limit"), ("insufficient_quota", False, "billing")],
)
async def test_sdk_preempted_stream_error_keeps_metadata_and_safe_message(code, retry, category):
    import httpx
    from openai import APIError

    # The SDK intercepts data.error before yielding an event to our parser.
    error = APIError(
        PRIVATE,
        request=httpx.Request("POST", "https://fixture.example/responses"),
        body={"code": code, "message": PRIVATE},
    )
    stream = Stream(error)
    provider, _create = provider_with(stream)
    response = await provider.chat_stream([{"role": "user", "content": "fixture"}])
    assert response.error_code == code
    assert response.error_should_retry is retry
    assert public_error_kind(response) == category
    assert PRIVATE not in response.content
    assert stream.closed


async def test_sdk_wrapped_error_body_keeps_its_available_status_and_retry_header():
    import httpx
    from openai import APIError

    error = APIError(
        PRIVATE,
        request=httpx.Request("POST", "https://fixture.example/responses"),
        body={
            "error": {"code": "rate_limit_exceeded", "message": PRIVATE},
            "status_code": 429,
            "headers": {"Retry-After": "2"},
        },
    )
    provider, _create = provider_with(Stream(error))
    result = await provider.chat_stream([{"role": "user", "content": "fixture"}])
    assert result.error_status_code == 429
    assert result.error_retry_after_s == 2
    assert PRIVATE not in result.content


@pytest.mark.parametrize("kind", ["timeout", "connection"])
async def test_sdk_transport_error_without_api_body_keeps_transport_classification(kind):
    import httpx
    from openai import APIConnectionError, APITimeoutError

    request = httpx.Request("POST", "https://fixture.example/responses")
    error = APITimeoutError(request) if kind == "timeout" else APIConnectionError(request=request)
    stream = Stream(error)
    provider, _create = provider_with(stream)
    result = await provider.chat_stream([{"role": "user", "content": "fixture"}])
    assert result.error_kind == kind
    assert public_error_kind(result) == kind
    assert is_transient_response(result)
    assert stream.closed
