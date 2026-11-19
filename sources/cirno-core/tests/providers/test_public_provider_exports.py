"""Lazy public exports point at current modules without creating provider clients."""

from importlib.util import find_spec, resolve_name
from unittest.mock import Mock

import pytest
from cirno_core import providers


@pytest.mark.parametrize("name", providers.__all__)
def test_public_provider_export_module_exists(name):
    module = providers._LAZY_IMPORTS[name]
    absolute = resolve_name(module, providers.__name__) if module.startswith(".") else module
    assert find_spec(absolute) is not None


def test_public_bedrock_export_is_current_class_without_creating_client(monkeypatch):
    from cirno_core.providers.bedrock.provider import BedrockProvider

    construct = Mock(side_effect=AssertionError("Export lookup must not create a client"))
    monkeypatch.setattr(BedrockProvider, "__init__", construct)
    assert providers.BedrockProvider is BedrockProvider
    construct.assert_not_called()


def test_unknown_public_provider_export_remains_an_attribute_error():
    with pytest.raises(AttributeError):
        getattr(providers, "MissingProvider")
