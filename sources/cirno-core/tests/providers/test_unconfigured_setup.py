"""Fresh installs must fail locally with setup guidance, never provider retries."""
from unittest.mock import AsyncMock

import pytest

from cirno_core.config.schema import Config
from cirno_core.providers.errors import public_error_kind
from cirno_core.providers.factory import build_unconfigured_provider_snapshot, validate_provider_setup


def test_fresh_install_has_no_invented_model_and_uses_keyless_search():
    config = Config()
    assert config.agents.defaults.model == ""
    assert config.tools.web.search.provider == "duckduckgo"
    with pytest.raises(ValueError, match="No model configured"):
        validate_provider_setup(config)


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_mode", ["standard", "persistent"])
async def test_setup_failure_never_enters_retry_loop(retry_mode):
    provider = build_unconfigured_provider_snapshot(Config(), "No model configured").provider
    provider.chat = AsyncMock(wraps=provider.chat)
    statuses = AsyncMock()
    result = await provider.chat_stream_with_retry(
        messages=[{"role": "user", "content": "hello"}],
        model="", retry_mode=retry_mode, on_retry_status=statuses,
    )
    assert result.finish_reason == "error"
    assert public_error_kind(result) == "configuration"
    assert result.error_should_retry is False
    provider.chat.assert_awaited_once()
    statuses.assert_not_awaited()
    assert "Settings" in result.content
