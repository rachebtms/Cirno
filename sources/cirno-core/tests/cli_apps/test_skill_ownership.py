"""App management must preserve unrelated owner-created Skill folders."""

import pytest
from cirno_core.apps.cli import paths
from cirno_core.apps.cli.contracts import CliAppError
from cirno_core.apps.cli.service import CliAppManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "get_home_path", lambda: tmp_path)
    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / "state")
    monkeypatch.setattr(manager, "_fetch_skill_content", lambda app: None)
    monkeypatch.setattr(manager.commands, "which", lambda name: None)
    return manager


def user_skill(manager, *, suffixed=False):
    name = paths._suffixed_skill_name("research") if suffixed else "cli-app-research"
    skill = manager.workspace / "skills" / name / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(f"---\nname: {name}\ndescription: My research skill\n---\nOwner notes\n")
    (skill.parent / "notes.txt").write_text("keep my data")
    return skill


def test_install_uses_separate_path_for_unowned_legacy_skill(manager):
    original = user_skill(manager)
    before = original.read_bytes()
    published = manager.install_skill({"name": "research", "entry_point": "fixture"})
    assert published != original
    assert original.read_bytes() == before
    manager.remove_skill("research")
    assert not published.exists()
    assert original.read_bytes() == before
    assert (original.parent / "notes.txt").read_text() == "keep my data"


@pytest.mark.parametrize("suffixed", [False, True])
def test_remove_does_not_delete_unowned_skill(manager, suffixed):
    original = user_skill(manager, suffixed=suffixed)
    legacy = user_skill(manager) if suffixed else original
    before = original.read_bytes()
    manager.remove_skill("research")
    assert original.read_bytes() == before
    assert (original.parent / "notes.txt").is_file()
    assert (legacy.parent / "notes.txt").is_file()


def test_unowned_fallback_path_is_rejected_without_overwriting(manager):
    original = user_skill(manager, suffixed=True)
    user_skill(manager)
    before = original.read_bytes()
    with pytest.raises(CliAppError, match="not owned"):
        manager.install_skill({"name": "research", "entry_point": "fixture"})
    assert original.read_bytes() == before


def test_unowned_fallback_file_is_not_reported_as_installed_skill(manager):
    original = user_skill(manager, suffixed=True)
    user_skill(manager)
    app = {"name": "research", "entry_point": "fixture", "package_manager": "bundled"}
    assert paths.cli_app_skill_path("research") == original
    assert manager._app_payload(app, {"research": {}})["skill_installed"] is False
