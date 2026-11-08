"""Skill history publishes complete, distinguishable trees or reports the failure."""

import errno
import os
from pathlib import Path

import pytest

from cirno_core.skills import history
from cirno_core.skills.validation import validate_skill


@pytest.fixture
def skill(tmp_path):
    directory = tmp_path / "home/skills/example"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: example\ndescription: Example Skill\n---\nInstructions\n"
    )
    return directory


def test_file_boundaries_are_part_of_revision_identity(tmp_path, skill):
    (skill / "a").write_bytes(b"partb\0more")
    first = history.snapshot_skill(skill, tmp_path / "home")
    (skill / "a").write_bytes(b"part")
    (skill / "b").write_bytes(b"more")
    second = history.snapshot_skill(skill, tmp_path / "home")

    assert first["revision"] != second["revision"]
    assert (Path(first["path"]) / "a").read_bytes() == b"partb\0more"
    assert (Path(second["path"]) / "b").read_bytes() == b"more"


def test_empty_directories_are_retained_and_change_the_revision(tmp_path, skill):
    first = history.snapshot_skill(skill, tmp_path / "home")
    (skill / "assets").mkdir()
    second = history.snapshot_skill(skill, tmp_path / "home")

    assert first["revision"] != second["revision"]
    assert (Path(second["path"]) / "assets").is_dir()


@pytest.mark.parametrize("operation", ["validate", "snapshot"])
def test_unreadable_subdirectory_never_becomes_a_complete_snapshot(
    tmp_path, skill, monkeypatch, operation
):
    first = history.snapshot_skill(skill, tmp_path / "home")
    blocked = skill / "private"
    blocked.mkdir()
    (blocked / "data.txt").write_text("must not be silently omitted")
    original = os.scandir

    def scandir(path):
        if not isinstance(path, int) and Path(path) == blocked:
            raise PermissionError(errno.EACCES, "Cannot scan Skill subtree", str(blocked))
        return original(path)

    monkeypatch.setattr(os, "scandir", scandir)
    with pytest.raises(PermissionError, match="Cannot scan Skill subtree"):
        if operation == "validate":
            validate_skill(skill)
        else:
            history.snapshot_skill(skill, tmp_path / "home")
    assert len(history.skill_versions("example", tmp_path / "home")) == 1
    assert Path(first["path"]).is_dir()
    assert not list((tmp_path / "home/skills-history/example").glob(".snapshot-*"))


@pytest.mark.parametrize("failure", ["copy", "metadata", "publish"])
def test_failed_publication_preserves_prior_versions_and_removes_staging(
    tmp_path, skill, monkeypatch, failure
):
    first = history.snapshot_skill(skill, tmp_path / "home")
    (skill / "asset.txt").write_text("new version")

    def fail(*args, **kwargs):
        raise OSError("Skill history write failed")

    if failure == "copy":
        monkeypatch.setattr(history.shutil, "copyfile", fail)
    elif failure == "metadata":
        monkeypatch.setattr(history, "atomic_write_text", fail)
    else:
        original = Path.replace

        def replace(path, target):
            if path.parent.name.startswith(".snapshot-"):
                return fail()
            return original(path, target)

        monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(OSError, match="Skill history write failed"):
        history.snapshot_skill(skill, tmp_path / "home")

    root = tmp_path / "home/skills-history/example"
    assert len(history.skill_versions("example", tmp_path / "home")) == 1
    assert len(list(root.glob("*.json"))) == 1
    assert not list(root.glob(".snapshot-*"))
    assert (Path(first["path"]) / "SKILL.md").is_file()


@pytest.mark.parametrize("root_link", [True, False])
def test_symlinks_are_reported_without_copying_external_contents(
    tmp_path, skill, create_symlink, root_link
):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text("external instructions")
    (outside / "secret.txt").write_text("external data")
    if root_link:
        link = tmp_path / "example"
        create_symlink(link, outside, target_is_directory=True)
        target = link
    else:
        create_symlink(skill / "external", outside, target_is_directory=True)
        target = skill
    snapshot = history.snapshot_skill(target, tmp_path / "home")

    assert not snapshot["valid"]
    assert any("symbolic link" in error for error in snapshot["errors"])
    assert not (Path(snapshot["path"]) / "secret.txt").exists()
    assert not (Path(snapshot["path"]) / "external").exists()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="Requires POSIX named pipes")
def test_named_pipe_is_an_invalid_history_entry_without_being_opened(tmp_path, skill):
    os.mkfifo(skill / "events")
    snapshot = history.snapshot_skill(skill, tmp_path / "home")

    assert not snapshot["valid"]
    assert any("events is not a regular file" in error for error in snapshot["errors"])
    assert not (Path(snapshot["path"]) / "events").exists()
