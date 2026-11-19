"""Search key omission retains a secret; explicit empty optional keys remove it."""

import pytest
from cirno_core.config.schema import Config
from cirno_server.webui.settings.capabilities import update_web_search_settings
from cirno_server.webui.settings.contracts import WebUISettingsError


@pytest.mark.parametrize("empty", [False, True])
def test_optional_key_patch_distinguishes_omission_from_explicit_empty(empty):
    config = Config()
    config.tools.web.search.provider = "keenable"
    config.tools.web.search.api_key = "saved-fixture-key"
    query = {"provider": ["keenable"]}
    if empty:
        query["api_key"] = [""]
    changed, restart = update_web_search_settings(config, query)
    assert config.tools.web.search.api_key == ("" if empty else "saved-fixture-key")
    assert changed is empty
    assert restart is False


def test_required_key_rejects_explicit_empty_and_keeps_saved_value():
    config = Config()
    config.tools.web.search.provider = "deepseek"
    config.tools.web.search.api_key = "saved-fixture-key"
    with pytest.raises(WebUISettingsError, match="api_key is required"):
        update_web_search_settings(config, {"provider": ["deepseek"], "api_key": [""]})
    assert config.tools.web.search.api_key == "saved-fixture-key"
