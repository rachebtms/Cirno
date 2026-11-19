"""Provider diagnostic bodies are not ordinary retry/failover log messages."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.config.models import ModelPresetConfig
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.fallback_provider import FallbackProvider
from cirno_core.providers.retry import ProviderRetryExecutor, ProviderRetryPolicy
from loguru import logger

DETAIL = "HTTP 503 Authorization: Bearer PrivateKey2026; request fragment PrivatePrompt2026"


@pytest.mark.parametrize("mode", ["recovered", "exhausted", "persistent"])
async def test_retry_logs_keep_classification_without_upstream_body(mode):
    failure = LLMResponse(DETAIL, finish_reason="error", error_kind="server_error")
    policy = ProviderRetryPolicy(delays=(1,), identical_error_limit=1)
    executor = ProviderRetryExecutor(SimpleNamespace(retry_policy=policy))
    executor.wait = AsyncMock()
    call = AsyncMock(side_effect=[failure, LLMResponse("ok") if mode == "recovered" else failure])
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)), format="{message}")
    try:
        response = await executor.attempts(
            call, {}, [], retry_mode="persistent" if mode == "persistent" else "standard",
            on_retry_wait=None, on_retry_exhausted=None, on_retry_status=None,
        )
    finally:
        logger.remove(sink)
    if mode != "recovered":
        assert response is failure and response.content == DETAIL
    assert messages
    text = "\n".join(messages).lower()
    assert "privatekey2026" not in text
    assert "privateprompt2026" not in text
    assert "server" in text


class Provider(LLMProvider):
    def __init__(self, name, response):
        super().__init__(provider_name=name)
        self.response = response

    def get_default_model(self):
        return "fake-model"

    async def chat(self, **_kwargs):
        return self.response


@pytest.mark.parametrize("mode", ["primary-rejected", "backup-failed", "backup-succeeded"])
async def test_fallback_logs_do_not_publish_primary_or_backup_error_bodies(mode):
    failure = LLMResponse(DETAIL, finish_reason="error", error_kind="invalid_request" if mode == "primary-rejected" else "server_error")
    backup_failure = LLMResponse("PrivateBackup2026", finish_reason="error", error_kind="server_error")
    primary = Provider("primary", failure)
    backup = Provider("backup", LLMResponse("ok") if mode == "backup-succeeded" else backup_failure)
    wrapper = FallbackProvider(primary, [ModelPresetConfig(model="backup")], lambda _preset: backup)
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)), format="{message}")
    try:
        response = await wrapper.chat(messages=[])
    finally:
        logger.remove(sink)
        await wrapper.aclose()
    if mode == "primary-rejected":
        assert response is failure and response.content == DETAIL
    elif mode == "backup-failed":
        assert response.content == backup_failure.content
    else:
        assert response.content == "ok"
    text = "\n".join(messages).lower()
    assert "privatekey2026" not in text
    assert "privateprompt2026" not in text
    assert "privatebackup2026" not in text
    assert "unknown" in text if mode == "primary-rejected" else "server" in text
