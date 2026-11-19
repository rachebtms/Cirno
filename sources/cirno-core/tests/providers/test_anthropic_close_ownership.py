"""Client closure completes before a cancelled provider owner is released."""

import asyncio
from types import SimpleNamespace

import pytest
from cirno_core.providers.anthropic_provider import AnthropicProvider


@pytest.mark.parametrize("outcome", ["ok", "error"])
async def test_repeated_cancel_waits_for_anthropic_client_close(outcome):
    entered, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def close():
        entered.set()
        await release.wait()
        finished.set()
        if outcome == "error":
            raise OSError("fake close failed after cancellation")

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider._client = SimpleNamespace(close=close)
    task = asyncio.create_task(provider.aclose())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert finished.is_set()


async def test_ordinary_close_error_is_not_swallowed():
    problem = OSError("fake close error")

    async def close():
        raise problem

    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider._client = SimpleNamespace(close=close)
    with pytest.raises(OSError) as caught:
        await provider.aclose()
    assert caught.value is problem
