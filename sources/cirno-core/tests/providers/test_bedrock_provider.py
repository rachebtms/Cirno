"""Tests for the native AWS Bedrock Converse provider."""

from __future__ import annotations

from typing import Any

import pytest
from cirno_core.config.providers import ProvidersConfig
from cirno_core.config.schema import Config
from cirno_core.providers.bedrock.messages import tool_use_block
from cirno_core.providers.bedrock.provider import BedrockProvider
from cirno_core.providers.bedrock.requests import build_request
from cirno_core.providers.bedrock.responses import parse_response
from cirno_core.providers.bedrock.responses import usage as response_usage
from cirno_core.providers.registry import find_by_name


class FakeClient:
    def __init__(
        self,
        *,
        response: dict[str, Any] | None = None,
        stream_events: list[dict[str, Any]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.stream_events = stream_events or []
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response or {}

    def converse_stream(self, **kwargs):
        self.stream_calls.append(kwargs)
        if self.error:
            raise self.error
        return {"stream": iter(self.stream_events)}


class FakeBedrockError(Exception):
    def __init__(self) -> None:
        super().__init__("too many requests")
        self.response = {
            "ResponseMetadata": {
                "HTTPStatusCode": 429,
                "HTTPHeaders": {"retry-after": "3"},
            },
            "Error": {
                "Code": "ThrottlingException",
                "Message": "Rate exceeded",
            },
        }


def test_bedrock_provider_is_registered_and_matches_without_api_key() -> None:
    spec = find_by_name("bedrock")
    assert spec is not None
    assert spec.backend == "bedrock"
    assert spec.is_direct is True
    assert hasattr(ProvidersConfig(), "bedrock")

    cfg = Config.model_validate({
        "agents": {"defaults": {"model": "bedrock/global.anthropic.claude-opus-4-7"}},
        "providers": {"bedrock": {"region": "us-east-1"}},
    })

    assert cfg.get_provider_name() == "bedrock"
    assert cfg.get_provider().region == "us-east-1"


def test_opus_47_uses_adaptive_thinking_and_omits_temperature() -> None:
    kwargs = build_request(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model="bedrock/global.anthropic.claude-opus-4-7",
        max_tokens=2048,
        temperature=0.1,
        reasoning_effort="medium",
        tool_choice=None,
    )

    assert kwargs["modelId"] == "global.anthropic.claude-opus-4-7"
    assert kwargs["inferenceConfig"] == {"maxTokens": 2048}
    assert kwargs["additionalModelRequestFields"]["thinking"] == {
        "type": "adaptive",
        "effort": "medium",
    }


def test_generic_bedrock_model_keeps_temperature_and_skips_anthropic_thinking() -> None:
    kwargs = build_request(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model="bedrock/amazon.nova-lite-v1:0",
        max_tokens=1024,
        temperature=0.3,
        reasoning_effort="medium",
        tool_choice=None,
    )

    assert kwargs["modelId"] == "amazon.nova-lite-v1:0"
    assert kwargs["inferenceConfig"] == {"maxTokens": 1024, "temperature": 0.3}
    assert "additionalModelRequestFields" not in kwargs
    assert "toolConfig" not in kwargs


def test_build_kwargs_converts_messages_tools_and_tool_results() -> None:
    tools = [{
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
        },
    }]
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "read x"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "toolu_1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "x"}'},
            }],
        },
        {"role": "tool", "tool_call_id": "toolu_1", "name": "read_file", "content": "ok"},
        {"role": "user", "content": "continue"},
    ]

    kwargs = build_request(
        messages=messages,
        tools=tools,
        model="bedrock/anthropic.claude-opus-4-7",
        max_tokens=1024,
        temperature=0.7,
        reasoning_effort=None,
        tool_choice="required",
    )

    assert kwargs["system"] == [{"text": "You are helpful."}]
    assert kwargs["messages"][1]["content"] == [{
        "toolUse": {
            "toolUseId": "toolu_1",
            "name": "read_file",
            "input": {"path": "x"},
        }
    }]
    assert kwargs["messages"][2]["role"] == "user"
    assert kwargs["messages"][2]["content"][0]["toolResult"]["toolUseId"] == "toolu_1"
    assert kwargs["messages"][2]["content"][1] == {"text": "continue"}
    tool_spec = kwargs["toolConfig"]["tools"][0]["toolSpec"]
    assert tool_spec["name"] == "read_file"
    assert kwargs["toolConfig"]["toolChoice"] == {"any": {}}


def test_tool_use_block_repairs_history_tool_arguments() -> None:
    block = tool_use_block({
        "id": "toolu_1",
        "function": {"name": "read_file", "arguments": '{path:"foo.txt"}'},
    })

    assert block is not None
    assert block["toolUse"]["input"] == {"path": "foo.txt"}


def test_build_kwargs_keeps_tool_config_for_historical_tool_blocks_without_tools() -> None:
    messages = [
        {"role": "user", "content": "read x"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "toolu_1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path": "x"}'},
            }],
        },
        {"role": "tool", "tool_call_id": "toolu_1", "name": "read_file", "content": "ok"},
        {"role": "user", "content": "continue"},
    ]

    kwargs = build_request(
        messages=messages,
        tools=[],
        model="bedrock/anthropic.claude-opus-4-7",
        max_tokens=1024,
        temperature=0.7,
        reasoning_effort=None,
        tool_choice=None,
    )

    assert any("toolUse" in block for msg in kwargs["messages"] for block in msg["content"])
    assert any("toolResult" in block for msg in kwargs["messages"] for block in msg["content"])
    assert kwargs["toolConfig"]["tools"][0]["toolSpec"]["name"] == "cirno_noop"
    assert "toolChoice" not in kwargs["toolConfig"]


def test_parse_response_maps_text_tools_reasoning_usage_and_stop_reason() -> None:
    response = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {"reasoningContent": {"reasoningText": {"text": "think", "signature": "sig"}}},
                    {"text": "hello"},
                    {"toolUse": {"toolUseId": "t1", "name": "search", "input": {"q": "x"}}},
                ],
            }
        },
        "stopReason": "tool_use",
        "usage": {
            "inputTokens": 10,
            "outputTokens": 5,
            "totalTokens": 15,
            "cacheReadInputTokens": 2,
        },
    }

    result = parse_response(response)

    assert result.content == "hello"
    assert result.finish_reason == "tool_calls"
    assert result.usage is not None
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 5
    assert result.usage.cache_read_tokens == 2
    assert result.usage.cache_write_tokens is None
    assert result.reasoning_content == "think"
    assert result.thinking_blocks == [{"type": "thinking", "thinking": "think", "signature": "sig"}]
    assert result.tool_calls[0].id == "t1"
    assert result.tool_calls[0].arguments == {"q": "x"}


@pytest.mark.asyncio
async def test_chat_stream_retries_eof_without_stop_reason() -> None:
    client = FakeClient(stream_events=[
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "partial summary"}}},
    ])
    provider = BedrockProvider(region="us-east-1", client=client)
    provider.retry_policy.delays = (0,)

    result = await provider.chat_stream_with_retry([{"role": "user", "content": "summarize"}])

    assert result.finish_reason == "error"
    assert result.error_kind == "connection"
    assert len(client.stream_calls) == 2


@pytest.mark.asyncio
async def test_chat_stream_aggregates_text_tool_use_and_usage() -> None:
    client = FakeClient(stream_events=[
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "he"}}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "llo"}}},
        {
            "contentBlockStart": {
                "contentBlockIndex": 1,
                "start": {"toolUse": {"toolUseId": "t1", "name": "search"}},
            }
        },
        {
            "contentBlockDelta": {
                "contentBlockIndex": 1,
                "delta": {"toolUse": {"input": '{"q":'}},
            }
        },
        {
            "contentBlockDelta": {
                "contentBlockIndex": 1,
                "delta": {"toolUse": {"input": '"x"}'}},
            }
        },
        {"contentBlockStop": {"contentBlockIndex": 1}},
        {"messageStop": {"stopReason": "tool_use"}},
        {"metadata": {"usage": {"inputTokens": 3, "outputTokens": 4, "totalTokens": 7}}},
    ])
    provider = BedrockProvider(region="us-east-1", client=client)
    deltas: list[str] = []

    result = await provider.chat_stream(
        messages=[{"role": "user", "content": "hi"}],
        model="bedrock/anthropic.claude-opus-4-7",
        on_content_delta=lambda text: _append_delta(deltas, text),
    )

    assert deltas == ["he", "llo"]
    assert result.content == "hello"
    assert result.finish_reason == "tool_calls"
    assert result.usage is not None
    assert result.usage.input_tokens == 3
    assert result.usage.output_tokens == 4
    assert result.usage.total_tokens == 7
    assert result.tool_calls[0].name == "search"
    assert result.tool_calls[0].arguments == {"q": "x"}


async def _append_delta(deltas: list[str], text: str) -> None:
    deltas.append(text)


@pytest.mark.parametrize(
    ("wire_usage", "expected_read", "expected_write", "expected_input"),
    [
        ({"inputTokens": 5, "outputTokens": 1}, None, None, 5),
        (
            {
                "inputTokens": 5,
                "outputTokens": 1,
                "cacheReadInputTokens": 0,
                "cacheWriteInputTokens": 0,
            },
            0,
            0,
            5,
        ),
        (
            {
                "inputTokens": 5,
                "outputTokens": 1,
                "cacheReadInputTokens": 7,
                "cacheWriteInputTokens": 3,
            },
            7,
            3,
            15,
        ),
    ],
)
def test_bedrock_usage_preserves_cache_reporting_and_logical_input(
    wire_usage: dict[str, int],
    expected_read: int | None,
    expected_write: int | None,
    expected_input: int,
) -> None:
    usage = response_usage(wire_usage)

    assert usage is not None
    assert usage.cache_read_tokens == expected_read
    assert usage.cache_write_tokens == expected_write
    assert usage.input_tokens == expected_input


@pytest.mark.asyncio
async def test_chat_error_maps_retry_metadata() -> None:
    provider = BedrockProvider(region="us-east-1", client=FakeClient(error=FakeBedrockError()))

    result = await provider.chat(messages=[{"role": "user", "content": "hi"}])

    assert result.finish_reason == "error"
    assert result.error_status_code == 429
    assert result.error_should_retry is True
    assert result.error_code == "throttlingexception"
    assert result.retry_after == 3


def test_configured_bearer_keys_are_isolated_between_clients_and_environment(monkeypatch):
    pytest.importorskip("boto3")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "environment-key")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fixture-access")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fixture-secret")
    import os

    class SignedRequest(Exception):
        pass

    tokens = []

    def capture(request, **kwargs):
        tokens.append(request.headers["Authorization"])
        raise SignedRequest()

    clients = [BedrockProvider(api_key=key, region="us-east-1")._get_client()
               for key in ("first-key", "second-key", None)]
    try:
        for client in (clients[1], clients[0], clients[2], clients[0]):
            client.meta.events.register("before-send.bedrock-runtime.Converse", capture)
            with pytest.raises(SignedRequest):
                client.converse(modelId="fixture", messages=[{
                    "role": "user", "content": [{"text": "hello"}],
                }])
            client.meta.events.unregister("before-send.bedrock-runtime.Converse", capture)
        assert tokens == [b"Bearer second-key", b"Bearer first-key",
                          b"Bearer environment-key", b"Bearer first-key"]
        assert os.environ["AWS_BEARER_TOKEN_BEDROCK"] == "environment-key"
    finally:
        for client in clients:
            client.close()
