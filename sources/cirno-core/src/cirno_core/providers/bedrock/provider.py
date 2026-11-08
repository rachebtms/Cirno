# pyright: reportMissingTypeStubs=false
"""AWS Bedrock Converse provider."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from functools import partial
from threading import Lock
from typing import Any, cast

from cirno_core.providers.base import LLMProvider
from cirno_core.providers.bedrock.errors import handle_error
from cirno_core.providers.bedrock.requests import build_request
from cirno_core.providers.bedrock.responses import parse_response, parse_stream_event, stream_result
from cirno_core.providers.bedrock.stream import stream_events
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.images import prepare_message_images


class BedrockProvider(LLMProvider):
    """LLM provider using AWS Bedrock Runtime's Converse APIs."""

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "bedrock/global.anthropic.claude-opus-4-7",
        *,
        region: str | None = None,
        profile: str | None = None,
        extra_body: dict[str, Any] | None = None,
        client: Any | None = None,
        provider_name: str = "bedrock",
    ):
        super().__init__(api_key, api_base, provider_name=provider_name)
        self.default_model = default_model
        self.region = region or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        self.profile = profile
        self._extra_body = extra_body or {}
        self._client = client
        self._stream_client = client
        self._owns_client = client is None
        self._client_lock = Lock()

    def _get_client(self, *, stream: bool = False) -> Any:
        with self._client_lock:
            client = self._stream_client if stream else self._client
            if client is None:
                client = self._make_client(stream=stream)
                if stream:
                    self._stream_client = client
                else:
                    self._client = client
            return client

    def _take_clients(self) -> list[Any]:
        with self._client_lock:
            clients = [
                client for client in (self._client, self._stream_client) if client is not None
            ]
            self._client = self._stream_client = None
            return clients

    async def aclose(self) -> None:
        if self._owns_client:
            for client in await asyncio.to_thread(self._take_clients):
                await asyncio.to_thread(client.close)

    def _make_client(self, *, stream: bool = False) -> Any:
        try:
            import boto3
            from botocore.config import Config
            from botocore.session import Session
            from botocore.tokens import ScopedEnvTokenProvider
        except ImportError as exc:  # pragma: no cover - exercised only without boto3 installed
            raise RuntimeError(
                "AWS Bedrock provider requires boto3. Enable AWS Bedrock support in Settings → Providers."
            ) from exc

        session_kwargs: dict[str, Any] = {}
        if self.api_key:
            sdk_session = Session()
            sdk_session.register_component(
                "token_provider",
                ScopedEnvTokenProvider(
                    sdk_session,
                    environ={"AWS_BEARER_TOKEN_BEDROCK": self.api_key},
                ),
            )
            session_kwargs["botocore_session"] = sdk_session
        if self.profile:
            session_kwargs["profile_name"] = self.profile
        boto3_module = cast(Any, boto3)
        session = boto3_module.Session(**session_kwargs)

        read_timeout_s = self.stream_idle_timeout_s if stream else self.request_timeout_s
        client_kwargs: dict[str, Any] = {
            "config": Config(
                connect_timeout=self.request_timeout_s,
                read_timeout=read_timeout_s,
                retries={"total_max_attempts": 1},
            ),
        }
        if self.region:
            client_kwargs["region_name"] = self.region
        if self.api_base:
            client_kwargs["endpoint_url"] = self.api_base
        return session.client("bedrock-runtime", **client_kwargs)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        try:
            kwargs = build_request(
                await prepare_message_images(messages),
                tools,
                model,
                max_tokens,
                temperature,
                reasoning_effort,
                tool_choice,
                default_model=self.default_model,
                extra_body=self._extra_body,
            )
            client = await asyncio.to_thread(self._get_client)
            response = cast(
                dict[str, Any],
                await asyncio.to_thread(client.converse, **kwargs),
            )
            return parse_response(response)
        except Exception as e:
            return handle_error(e)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        on_content_delta: Callable[[str], Awaitable[None]] | None = None,
        on_thinking_delta: Callable[[str], Awaitable[None]] | None = None,
        on_tool_call_delta: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> LLMResponse:
        idle_timeout_s = self.stream_idle_timeout_s
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        thinking_blocks: list[dict[str, Any]] = []
        tool_buffers: dict[int, dict[str, Any]] = {}
        state: dict[str, Any] = {}

        try:
            kwargs = build_request(
                await prepare_message_images(messages),
                tools,
                model,
                max_tokens,
                temperature,
                reasoning_effort,
                tool_choice,
                default_model=self.default_model,
                extra_body=self._extra_body,
            )
            client = await asyncio.to_thread(self._get_client, stream=True)
            async with stream_events(
                partial(client.converse_stream, **kwargs), idle_timeout_s=idle_timeout_s
            ) as events:
                async for event in events:
                    delta = parse_stream_event(
                        event,
                        content_parts=content_parts,
                        reasoning_parts=reasoning_parts,
                        thinking_blocks=thinking_blocks,
                        tool_buffers=tool_buffers,
                        state=state,
                    )
                    if delta is not None:
                        if delta.text and on_content_delta:
                            await on_content_delta(delta.text)
                        if delta.thinking and on_thinking_delta:
                            await on_thinking_delta(delta.thinking)
                        if delta.tool is not None and on_tool_call_delta:
                            await on_tool_call_delta(delta.tool)
            if not state.get("stop_reason"):
                raise ConnectionError("Model stream ended before a stop reason was received")
            return stream_result(
                content_parts=content_parts,
                reasoning_parts=reasoning_parts,
                thinking_blocks=thinking_blocks,
                tool_buffers=tool_buffers,
                state=state,
            )
        except asyncio.TimeoutError:
            return LLMResponse(
                content=(
                    f"Error calling LLM: stream stalled for more than {idle_timeout_s:g} seconds"
                ),
                finish_reason="error",
                error_kind="timeout",
            )
        except Exception as e:
            return handle_error(e)

    def get_default_model(self) -> str:
        return self.default_model
