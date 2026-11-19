"""Dependency lockfiles are user data; only known service lock paths are omitted."""

import shutil
import tarfile

import pytest
from cirno_server.backup.archive import Backups


@pytest.mark.parametrize("folder", ["workspace/project", "home/skills/project", "state/tools/source"])
@pytest.mark.parametrize("kind", ["files", "directory"])
def test_backup_keeps_dependency_lockfiles_and_directories(tmp_path, folder, kind):
    tmp_path.joinpath("config.json").write_text("{}")
    project = tmp_path / folder
    project.mkdir(parents=True)
    if kind == "files":
        expected = ["Cargo.lock", "uv.lock", "yarn.lock", "poetry.lock"]
        for name in expected:
            project.joinpath(name).write_text("Pinned dependency data")
    else:
        project.joinpath("notes.lock").mkdir()
        project.joinpath("notes.lock", "research.txt").write_text("Research")
        expected = ["notes.lock/research.txt"]
    backup = Backups(tmp_path / "config.json")
    output, _ = backup.create([])
    with tarfile.open(output) as archive:
        names = set(archive.getnames())
    assert all("instance/" + folder + "/" + name in names for name in expected)
    if folder == "workspace/project" and kind == "files":
        upload = tmp_path.parent / (tmp_path.name + "-upload.tar.gz")
        shutil.copy2(output, upload)
        preview = backup.inspect(upload)
        project.joinpath("uv.lock").write_text("Changed dependency data")
        backup.prepare_restore(preview["id"], {})
        assert backup.apply_pending()
        assert project.joinpath("uv.lock").read_text() == "Pinned dependency data"


def test_backup_omits_known_runtime_locks_but_keeps_similarly_named_project_data(tmp_path):
    tmp_path.joinpath("custom.json").write_text("{}")
    locks = ["custom.json.lock", ".docker-bootstrap.lock", "state/run/gateway.json.lock",
             "state/run/gateway.json.transition.lock", "state/cron.lock", "state/tools/setup.lock",
             "state/tools/apt/record.lock", "state/credentials/records.lock", "state/migrations/.lock"]
    for name in locks:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("Runtime lock")
    kept = ["workspace/custom.json.lock", "state/run/start.lock", "state/cron/actions.lock"]
    for name in kept:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("User data")
    output, _ = Backups(tmp_path / "custom.json").create([])
    with tarfile.open(output) as archive:
        names = set(archive.getnames())
    assert not any("instance/" + name in names for name in locks)
    assert all("instance/" + name in names for name in kept)
