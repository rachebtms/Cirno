import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import cirno_server.webui.sidebar_state as sidebar_state
import pytest
from cirno_server.webui.sidebar_state import (
    default_webui_sidebar_state,
    read_webui_sidebar_state,
    webui_sidebar_state_path,
    write_webui_sidebar_state,
)


def test_sidebar_state_defaults_when_file_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path)

    state = read_webui_sidebar_state()

    assert state == default_webui_sidebar_state()
    assert webui_sidebar_state_path() == tmp_path / "webui" / "sidebar-state.json"


def test_sidebar_state_normalizes_partial_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path)
    path = webui_sidebar_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "pinned_keys": ["websocket:a", "websocket:a", "", 123],
                "archived_keys": ["websocket:b"],
                "session_order": ["websocket:b", "websocket:a", "websocket:b"],
                "title_overrides": {"websocket:a": "  Release notes  ", "bad": ""},
                "project_name_overrides": {"/repo": "  Core  ", "bad": ""},
                "tags_by_key": {"websocket:a": ["work", "work", ""]},
                "collapsed_groups": {"Earlier": 1},
                "view": {
                    "density": "tiny",
                    "show_archived": True,
                    "sort": "nope",
                    "show_previews": True,
                    "show_timestamps": True,
                },
            }
        ),
        encoding="utf-8",
    )

    state = read_webui_sidebar_state()

    assert state["schema_version"] == 2
    assert state["pinned_keys"] == ["websocket:a"]
    assert state["archived_keys"] == ["websocket:b"]
    assert state["session_order"] == ["websocket:b", "websocket:a"]
    assert state["title_overrides"] == {"websocket:a": "Release notes"}
    assert state["project_name_overrides"] == {"/repo": "Core"}
    assert state["tags_by_key"] == {"websocket:a": ["work"]}
    assert state["collapsed_groups"] == {"Earlier": True}
    assert state["view"] == {
        "density": "comfortable",
        "show_archived": True,
        "sort": "updated_desc",
    }


def test_sidebar_state_write_is_scoped_to_config_data_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path)

    state = write_webui_sidebar_state(
        {
            "pinned_keys": ["websocket:a"],
            "archived_keys": ["websocket:b"],
            "session_order": ["websocket:b", "websocket:a"],
            "title_overrides": {"websocket:a": "Release"},
            "project_name_overrides": {"/repo": "Core"},
            "view": {"density": "compact", "sort": "manual"},
        }
    )

    assert state["pinned_keys"] == ["websocket:a"]
    assert state["archived_keys"] == ["websocket:b"]
    assert state["session_order"] == ["websocket:b", "websocket:a"]
    assert state["title_overrides"] == {"websocket:a": "Release"}
    assert state["project_name_overrides"] == {"/repo": "Core"}
    assert state["view"]["density"] == "compact"
    assert state["view"]["sort"] == "manual"
    assert webui_sidebar_state_path().is_file()
    assert read_webui_sidebar_state() == state


def test_concurrent_preference_writes_publish_whole_records(tmp_path, monkeypatch):
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path)
    payloads = [{"pinned_keys": [f"websocket:{index}"],
                 "title_overrides": {f"websocket:{index}": f"Research {index}"}} for index in range(12)]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(write_webui_sidebar_state, payloads))
    assert [result["pinned_keys"] for result in results] == [payload["pinned_keys"] for payload in payloads]
    assert read_webui_sidebar_state() in results
    assert list(webui_sidebar_state_path().parent.iterdir()) == [webui_sidebar_state_path()]


@pytest.mark.parametrize("content", [b'{"bad":', b'["wrong root"]', b" " * (256 * 1024 + 1)])
def test_unreadable_preferences_are_reported_without_replacing_the_file(tmp_path, monkeypatch, content):
    from cirno_server.webui.http.sidebar import SidebarRoutes
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path)
    path = webui_sidebar_state_path()
    path.write_bytes(content)
    with pytest.raises(ValueError):
        read_webui_sidebar_state()
    server = SimpleNamespace(check_api_token=lambda request: True, _log=Mock())
    response = SidebarRoutes(server)._handle_webui_sidebar_state(None)
    assert response.status_code == 500
    assert b"failed to read conversation preferences" in response.body
    assert path.read_bytes() == content


def test_failed_atomic_preference_write_reaches_the_caller(tmp_path, monkeypatch):
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path)
    write_webui_sidebar_state({"pinned_keys": ["websocket:a"]})
    path = webui_sidebar_state_path()
    original = path.read_bytes()
    def reject_write(*args):
        raise OSError("Disk full")
    monkeypatch.setattr(sidebar_state, "atomic_write_bytes", reject_write)
    with pytest.raises(OSError, match="Disk full"):
        write_webui_sidebar_state({"pinned_keys": ["websocket:b"]})
    assert path.read_bytes() == original
