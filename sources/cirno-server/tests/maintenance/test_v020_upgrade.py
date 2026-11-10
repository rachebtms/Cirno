"""A patch upgrade retains owner data and resumes interrupted configuration installs."""

import json
from pathlib import Path

import pytest
from cirno_core import __version__
from cirno_core.notifications.inbox import NotificationInbox
from cirno_server.maintenance.migrations.registry import migrate_instance


@pytest.mark.parametrize("source", ["0.2.0", "0.2.1", "0.2.2", "0.2.3", "0.2.4", "0.2.5", "0.2.6"])
@pytest.mark.parametrize("interrupt", [False, True])
def test_v020_upgrade_preserves_state_and_is_resumable(tmp_path, monkeypatch, interrupt, source):
    config = {"lastRunVersion": source, "providers": {"custom": {"apiKey": "owner-key"}},
              "agents": {"defaults": {"workspace": str(tmp_path / "workspace")}}}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    original = path.read_bytes()
    owned = {"home/SOUL.md": "Owner personality", "home/USER.md": "Owner profile",
             "home/memory/MEMORY.md": "Recorded fact", "workspace/paper.md": "Research"}
    for name, text in owned.items():
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
    rename = Path.rename

    def fail_install(self, target):
        if self.name == "config.json" and self.parent.name == "staged":
            raise OSError("Interrupted patch installation")
        return rename(self, target)

    if interrupt:
        with monkeypatch.context() as patch:
            patch.setattr(Path, "rename", fail_install)
            with pytest.raises(OSError, match="Interrupted patch installation"):
                migrate_instance(path)
        assert not path.exists()
    assert migrate_instance(path)
    assert json.loads(path.read_text()) == {**config, "lastRunVersion": __version__}
    assert not migrate_instance(path)
    target = {"0.2.0": "0.2.1", "0.2.1": "0.2.2", "0.2.2": "0.2.3", "0.2.3": "0.2.4", "0.2.4": "0.2.5", "0.2.5": "0.2.6", "0.2.6": "0.2.7"}[source]
    assert (tmp_path / f"state/migrations/{source}-to-{target}/originals/target-0").read_bytes() == original
    for name, text in owned.items():
        assert (tmp_path / name).read_text() == text
    assert not (tmp_path / "home/BOOTSTRAP.md").exists()
    notices = NotificationInbox(tmp_path / "state").list(category="system")["items"]
    assert len(notices) == {"0.2.0": 7, "0.2.1": 6, "0.2.2": 5, "0.2.3": 4, "0.2.4": 3, "0.2.5": 2, "0.2.6": 1}[source]
    assert "profiles and settings retained" in notices[0]["body"]
    assert "Imported" not in notices[0]["body"]
