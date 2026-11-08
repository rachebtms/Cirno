"""Old layout retirement preserves preferences and an exact recoverable original."""

import json

import pytest
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_server.maintenance.migrations.registry import migrate_instance


def test_released_preferences_preserve_titles_and_archive_the_old_layout(released):
    instance, _, config = released
    path = instance / "state/webui/sidebar-state.json"
    path.parent.mkdir(parents=True)
    raw = {"schema_version": 1, "pinned_keys": ["websocket:global", "websocket:worker"],
           "archived_keys": ["websocket:other"], "title_overrides": {"websocket:worker": "Research"},
           "workbench": {"version": 1, "tabs": {"old": {"paneKeys": ["websocket:worker"]}}},
           "view": {"sort": "title_asc", "show_archived": True}}
    path.write_text(json.dumps(raw), encoding="utf-8")
    original = path.read_bytes()
    assert migrate_instance(config)
    saved = json.loads(path.read_text())
    assert saved["schema_version"] == 2
    assert saved["pinned_keys"] == [ROUTER_SESSION_KEY, "websocket:worker"]
    assert saved["archived_keys"] == ["websocket:other"]
    assert saved["title_overrides"] == {"websocket:worker": "Research"}
    assert saved["view"]["sort"] == "title_asc"
    assert saved["view"]["show_archived"] is True
    assert "workbench" not in saved
    root = instance / "state/migrations/0.1.6-to-0.2.0"
    assert any(path.read_bytes() == original for path in (root / "originals").iterdir() if path.is_file())
    assert json.loads((root / "report.json").read_text())["retired_chat_groups"] == 1
    assert not migrate_instance(config)


@pytest.mark.parametrize("content", ['{"bad":', '["not an object"]'])
def test_invalid_released_preferences_stop_import_before_replacing_data(released, content):
    instance, _, config = released
    path = instance / "state/webui/sidebar-state.json"
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    original_config = config.read_bytes()
    with pytest.raises(ValueError):
        migrate_instance(config)
    assert config.read_bytes() == original_config
    assert path.read_text() == content
