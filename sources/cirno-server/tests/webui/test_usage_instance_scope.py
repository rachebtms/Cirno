"""Settings usage reads follow their configuration, not global selection."""

from types import SimpleNamespace

import pytest
from cirno_core.config.loader import load_config, set_config_path
from cirno_server.webui.settings import api, system


@pytest.mark.parametrize("entry", ["overview", "usage"])
def test_usage_settings_read_the_selected_server_instance(tmp_path, monkeypatch, entry):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    source = first / "settings.json"
    source.write_text("{}")
    set_config_path(second / "config.json")
    monkeypatch.setattr(system, "workspace_sandbox_status", lambda **_kwargs: SimpleNamespace(as_dict=lambda: {}))
    observed = []

    def usage(path, **_kwargs):
        observed.append(path)
        return {"owner": str(path)}

    monkeypatch.setattr(system, "llm_usage_payload", usage)
    if entry == "overview":
        result = system.system_settings_payload(load_config(source), config_path=source, version="fixture")["usage"]
    else:
        result = api.settings_usage_payload(config_path=source)
    assert observed == [first / "state" / "llm_usage.sqlite3"]
    assert result["owner"] == str(observed[0])
    assert not (second / "state").exists()
