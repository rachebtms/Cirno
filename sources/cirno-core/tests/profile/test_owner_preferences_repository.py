"""Durable owner preferences shared by independent browser connections."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from cirno_core.profile.preferences import PreferenceConflictError, PreferencesRepository


def test_default_theme_contains_day_and_night_palettes(tmp_path):
    saved = PreferencesRepository(tmp_path / "preferences.sqlite3").read()
    assert saved["values"]["themeId"] == "cirno-snow"
    snow = next(theme for theme in saved["themes"] if theme["id"] == "cirno-snow")
    assert snow["light"]["background"] != snow["dark"]["background"]
    assert snow["light"].keys() == snow["dark"].keys()
    assert saved["values"]["memoryGraphLimit"] == 300


def test_preferences_survive_restart_and_workspace_changes(tmp_path):
    path = tmp_path / "state" / "preferences.sqlite3"
    PreferencesRepository(path).update(
        {"language": "zh-CN", "themeMode": "dark", "readingTextSize": "large",
         "launcherOrder": ["credentials", "cirno", "files"], "memoryGraphLimit": 1200}
    )
    loaded = PreferencesRepository(path).read()
    assert loaded["values"]["language"] == "zh-CN"
    assert loaded["values"]["themeMode"] == "dark"
    assert loaded["values"]["readingTextSize"] == "large"
    assert loaded["values"]["launcherOrder"] == ["credentials", "cirno", "files"]
    assert loaded["values"]["memoryGraphLimit"] == 1200
    assert loaded["revision"] == 1


def test_parallel_devices_preserve_unrelated_field_updates(tmp_path):
    path = tmp_path / "preferences.sqlite3"
    first, second = PreferencesRepository(path), PreferencesRepository(path)
    with ThreadPoolExecutor(2) as pool:
        futures = [
            pool.submit(first.update, {"themeMode": "dark"}),
            pool.submit(second.update, {"codeWrap": False}),
        ]
        for future in futures:
            future.result()
    saved = first.read()
    assert saved["values"]["themeMode"] == "dark"
    assert saved["values"]["codeWrap"] is False
    assert saved["revision"] == 2


def test_theme_edit_conflict_does_not_erase_other_device_changes(tmp_path):
    store = PreferencesRepository(tmp_path / "preferences.sqlite3")
    original = store.read()
    store.update({"themeMode": "dark"})
    with pytest.raises(PreferenceConflictError):
        store.update({"themeMode": "light"}, expected_revision=original["revision"])
    assert store.read()["values"]["themeMode"] == "dark"


def test_custom_palette_round_trip_and_invalid_edit_rollback(tmp_path):
    store = PreferencesRepository(tmp_path / "preferences.sqlite3")
    custom = {**store.read()["themes"][0], "id": "my-snow", "name": "My snow"}
    saved = store.update({"customThemes": [custom], "themeId": custom["id"]})
    invalid = {**custom, "dark": {**custom["dark"], "accent": "invalid"}}
    with pytest.raises(ValueError):
        store.update({"customThemes": [invalid]})
    assert store.read() == saved
    assert PreferencesRepository(store.path).read()["values"]["customThemes"] == [custom]


@pytest.mark.parametrize(
    "patch",
    [
        {"themeId": "missing"},
        {"unrecognizedField": True},
        {"themeMode": "invalid"},
        {"customReadingTextSize": 900},
        {"memoryGraphLimit": 0},
        {"memoryGraphLimit": -1},
        {"memoryGraphLimit": 1.5},
        {"memoryGraphLimit": True},
    ],
)
def test_rejects_invalid_updates_without_changing_revision(tmp_path, patch):
    store = PreferencesRepository(tmp_path / "preferences.sqlite3")
    original = store.read()
    with pytest.raises(ValueError):
        store.update(patch)
    assert store.read() == original


def test_builtin_theme_cannot_be_replaced(tmp_path):
    store = PreferencesRepository(tmp_path / "preferences.sqlite3")
    with pytest.raises(ValueError):
        store.update({"customThemes": [store.read()["themes"][0]]})
