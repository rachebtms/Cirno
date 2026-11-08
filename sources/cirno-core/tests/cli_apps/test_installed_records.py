"""CLI installation metadata survives independent concurrent managers."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from cirno_core.apps.cli.contracts import CliAppError
from cirno_core.apps.cli.records import InstalledApps


def test_parallel_installs_and_remove_do_not_overwrite_other_apps(tmp_path):
    path = tmp_path / "apps" / "installed.json"
    InstalledApps(path).put("removed", {"entry_point": "old-cli"})

    def put(index):
        store = InstalledApps(path)
        store.put(f"app-{index}", {"entry_point": f"command-{index}"})
        store.remove("removed")

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(put, range(24)))
    apps = InstalledApps(path).read()
    assert set(apps) == {f"app-{index}" for index in range(24)}
    assert all(apps[f"app-{index}"]["entry_point"] == f"command-{index}" for index in range(24))


@pytest.mark.parametrize("payload", ["{broken", '{"gimp": {}}', '{"schema_version": 2, "apps": {}}'])
def test_invalid_install_state_is_reported_and_left_unchanged(tmp_path, payload):
    path = tmp_path / "installed.json"
    path.write_text(payload)
    with pytest.raises(CliAppError):
        InstalledApps(path).put("sample", {"entry_point": "sample"})
    assert path.read_text() == payload
