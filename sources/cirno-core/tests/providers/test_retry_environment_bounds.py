"""The environment entry point obeys the same retry bounds as settings."""

import pytest
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse


class Provider(LLMProvider):
    async def chat(self, **_kwargs):
        return LLMResponse("unused")

    def get_default_model(self):
        return "fake-model"


@pytest.mark.parametrize("value", ["2", "21", "128"])
def test_out_of_range_environment_retries_are_rejected(monkeypatch, value):
    monkeypatch.setenv("CIRNO_PROVIDER_MAX_RETRIES", value)
    with pytest.raises(ValueError):
        Provider(provider_name="fake")


@pytest.mark.parametrize("value", [3, 20])
def test_valid_environment_retry_boundaries_match_settings(monkeypatch, value):
    monkeypatch.setenv("CIRNO_PROVIDER_MAX_RETRIES", str(value))
    provider = Provider(provider_name="fake")
    assert provider.retry_policy.delays == tuple(min(2 ** index, 60) for index in range(value))


def test_environment_retry_policies_remain_instance_owned(monkeypatch):
    monkeypatch.setenv("CIRNO_PROVIDER_MAX_RETRIES", "3")
    first = Provider(provider_name="first")
    monkeypatch.setenv("CIRNO_PROVIDER_MAX_RETRIES", "5")
    second = Provider(provider_name="second")
    monkeypatch.delenv("CIRNO_PROVIDER_MAX_RETRIES")
    third = Provider(provider_name="third")
    assert len(first.retry_policy.delays) == 3
    assert len(second.retry_policy.delays) == 5
    assert third.retry_policy.delays == (1, 2, 4)
