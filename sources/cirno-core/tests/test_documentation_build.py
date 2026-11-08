"""Standalone distributions preserve resources across source and wheel builds."""

import importlib.util
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

REPOSITORY = Path(__file__).resolve().parents[3]


def build(directory, target):
    result = subprocess.run(
        [sys.executable, "-c", f"import hatchling.build; hatchling.build.build_{target}('dist')"],
        cwd=directory, env={**os.environ, "CIRNO_SKIP_WEBUI_BUILD": "1"}, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def fixture_package(root, name):
    folder = root / "sources" / f"cirno-{name}"
    folder.mkdir(parents=True)
    for file in ["pyproject.toml", "hatch_build.py", "LICENSE", "THIRD_PARTY_NOTICES.md"]:
        shutil.copyfile(REPOSITORY / "sources" / f"cirno-{name}" / file, folder / file)
    package = folder / "src" / f"cirno_{name}"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('"""Package fixture."""')
    return folder


def test_editable_build_does_not_copy_generated_resources_into_source(tmp_path):
    root = fixture_package(tmp_path, "core")
    spec = importlib.util.spec_from_file_location("core_build_test", root / "hatch_build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hook = module.CoreBuildHook(str(root), {}, None, {}, "", "wheel", SimpleNamespace())
    before = set(root.iterdir())
    data = {}
    hook.initialize("editable", data)
    assert set(root.iterdir()) == before
    assert data == {}


@pytest.mark.parametrize("package", ["core", "server"])
def test_source_distribution_rebuild_preserves_owned_resources(tmp_path, package):
    folder = fixture_package(tmp_path, package)
    if package == "core":
        docs = tmp_path / "documents"
        docs.mkdir()
        (docs / "README.md").write_text("Current documentation")
        resource = "cirno_core/skills/builtin/cirno-document/references/README.md"
        expected = b"Current documentation"
    else:
        bundle = tmp_path / "build/webui/index.html"
        bundle.parent.mkdir(parents=True)
        bundle.write_text("<html>Browser UI</html>")
        resource = "cirno_server/web/dist/index.html"
        expected = b"<html>Browser UI</html>"
    build(folder, "sdist")
    with tarfile.open(next((folder / "dist").glob("*.tar.gz"))) as archive:
        archive.extractall(tmp_path / "unpacked", filter="data")
    unpacked = next((tmp_path / "unpacked").iterdir())
    build(unpacked, "wheel")
    with ZipFile(next((unpacked / "dist").glob("*.whl"))) as wheel:
        assert wheel.namelist().count(resource) == 1
        assert wheel.read(resource) == expected
        assert not any("/tests/" in name or "__pycache__" in name for name in wheel.namelist())
    assert not (folder / "src/cirno_core/_build_commit.txt").exists()
    assert not (folder / "src/cirno_core/skills/builtin/cirno-document/references").exists()


@pytest.mark.parametrize("package", ["core", "server"])
def test_editable_wheel_uses_the_same_canonical_source_root_as_static_analysis(tmp_path, package):
    folder = fixture_package(tmp_path, package)
    build(folder, "editable")
    with ZipFile(next((folder / "dist").glob("*.whl"))) as wheel:
        paths = [name for name in wheel.namelist() if name.endswith(".pth")]
        assert len(paths) == 1
        assert wheel.read(paths[0]).decode().strip() == str(folder / "src")
        assert not any(name.startswith("_editable_impl_") and name.endswith(".py") for name in wheel.namelist())
