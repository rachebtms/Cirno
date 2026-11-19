"""Missing staged extras must never remove the owner's existing target."""

import io
import shutil
import tarfile

import pytest
from cirno_server.backup.archive import Backups


@pytest.mark.parametrize("phase", ["prepare", "apply"])
@pytest.mark.parametrize("change", ["missing", "file", "link"])
def test_missing_staged_extra_preserves_existing_target(tmp_path, phase, change):
    root, extra = tmp_path / "instance", tmp_path / "extra"
    root.mkdir()
    extra.mkdir()
    root.joinpath("config.json").write_text("{}")
    extra.joinpath("research.txt").write_text("Original research")
    backup = Backups(root / "config.json")
    exported, _ = backup.create([str(extra)])
    upload = tmp_path / "upload.tar.gz"
    shutil.copy2(exported, upload)
    preview = backup.inspect(upload)
    stage = backup._stage(preview["id"])
    if phase == "apply":
        backup.prepare_restore(preview["id"], {"extras/0": str(extra)})
    shutil.rmtree(stage / "extras" / "0")
    if change == "file":
        (stage / "extras" / "0").write_text("Wrong type")
    elif change == "link":
        (stage / "extras" / "0").symlink_to(extra, target_is_directory=True)
    try:
        if phase == "prepare":
            with pytest.raises(ValueError, match="extra"):
                backup.prepare_restore(preview["id"], {"extras/0": str(extra)})
        else:
            with pytest.raises((ValueError, FileNotFoundError)):
                backup.apply_pending()
    finally:
        assert extra.joinpath("research.txt").read_text() == "Original research"
        assert root.joinpath("config.json").read_text() == "{}"


def test_import_rejects_manifest_extra_without_a_matching_archive_root(tmp_path):
    root, extra = tmp_path / "instance", tmp_path / "extra"
    root.mkdir()
    extra.mkdir()
    root.joinpath("config.json").write_text("{}")
    extra.joinpath("research.txt").write_text("Original research")
    backup = Backups(root / "config.json")
    exported, _ = backup.create([str(extra)])
    upload = tmp_path / "upload.tar.gz"
    with tarfile.open(exported) as source, tarfile.open(upload, "w:gz") as target:
        for member in source:
            if member.name == "extras/0" or member.name.startswith("extras/0/"):
                continue
            target.addfile(member, io.BytesIO(source.extractfile(member).read()) if member.isfile() else None)
    with pytest.raises(ValueError, match="extra-folder source"):
        backup.inspect(upload)
    assert not upload.exists()
    assert not list((backup.store / "staging").iterdir())
    assert extra.joinpath("research.txt").read_text() == "Original research"


def test_extra_file_copy_failure_keeps_the_previous_target_contents(tmp_path, monkeypatch):
    root, extra = tmp_path / "instance", tmp_path / "extra"
    root.mkdir()
    extra.mkdir()
    root.joinpath("config.json").write_text("{}")
    extra.joinpath("research.txt").write_text("Backup version")
    backup = Backups(root / "config.json")
    exported, _ = backup.create([str(extra)])
    upload = tmp_path / "upload.tar.gz"
    shutil.copy2(exported, upload)
    preview = backup.inspect(upload)
    backup.prepare_restore(preview["id"], {"extras/0": str(extra)})
    extra.joinpath("research.txt").write_text("Current research")
    copy = shutil.copy2

    def failed_copy(source, target, **kwargs):
        if source == backup._stage(preview["id"]) / "extras" / "0" / "research.txt":
            raise OSError("Fixture source copy failed")
        return copy(source, target, **kwargs)

    monkeypatch.setattr("cirno_server.backup.archive.shutil.copy2", failed_copy)
    with pytest.raises(OSError, match="Fixture source copy failed"):
        backup.apply_pending()
    assert extra.joinpath("research.txt").read_text() == "Current research"
    assert not list(extra.glob(".cirno-restore-*.tmp"))
