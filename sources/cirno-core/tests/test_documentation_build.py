"""Release resources must not create generated files in the source package."""

from pathlib import Path
from types import SimpleNamespace
import subprocess
import os
import shutil
import sys
import tarfile
from zipfile import ZipFile

from hatch_build import WebUIBuildHook


def project(root):
    docs = root / "documents"
    docs.mkdir()
    (docs / "README.md").write_text("Document index", encoding="utf-8")
    (docs / "configuration.md").write_text("Configure a model", encoding="utf-8")
    (docs / "examples").mkdir()
    (docs / "examples/config.json").write_text("{}", encoding="utf-8")
    core = root / "sources/cirno-core"
    core.mkdir(parents=True)
    (core / "__init__.py").write_text("", encoding="utf-8")
    return core, WebUIBuildHook(str(root), {}, None, {}, "", "wheel",
                               SimpleNamespace(display_info=lambda message: None))


def test_editable_install_does_not_copy_documents_into_source(tmp_path):
    core, hook = project(tmp_path)
    build_data = {}
    hook.initialize("editable", build_data)
    assert sorted(path.name for path in core.iterdir()) == ["__init__.py"]
    assert any(name.endswith(".pth") for name in build_data["force_include"].values())


def test_source_distribution_rebuild_has_one_bundle_and_bundled_documents(tmp_path):
    core, _ = project(tmp_path)
    repository = Path(__file__).resolve().parents[3]
    for name in ("pyproject.toml", "hatch_build.py", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(repository / name, tmp_path / name)
    bundle = core / "web/dist/index.html"
    bundle.parent.mkdir(parents=True)
    bundle.write_text("<html>Cirno package</html>", encoding="utf-8")
    environment = {**os.environ, "CIRNO_SKIP_WEBUI_BUILD": "1"}
    def build(directory, target):
        result = subprocess.run([sys.executable, "-c", f"import hatchling.build; hatchling.build.build_{target}('dist')"],
                                cwd=directory, env=environment, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    build(tmp_path, "sdist")
    with tarfile.open(next((tmp_path / "dist").glob("*.tar.gz"))) as archive:
        archive.extractall(tmp_path / "extracted", filter="data")
    extracted = next((tmp_path / "extracted").iterdir())
    build(extracted, "wheel")
    with ZipFile(next((extracted / "dist").glob("*.whl"))) as wheel:
        assert wheel.namelist().count("cirno/web/dist/index.html") == 1
        assert wheel.read("cirno/skills/builtin/cirno-document/references/README.md") == b"Document index"
        assert wheel.read("cirno/skills/builtin/cirno-document/references/examples/config.json") == b"{}"


def test_release_embeds_docs_and_revision_without_writing_source(tmp_path, monkeypatch):
    core, hook = project(tmp_path)
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "--allow-empty", "-m", "Initial"], check=True, capture_output=True)
    monkeypatch.setenv("CIRNO_SKIP_WEBUI_BUILD", "1")
    build_data = {}
    hook.initialize("standard", build_data)
    artifacts = build_data["force_include"]
    assert artifacts[str(tmp_path / "documents/README.md")] == "cirno/skills/builtin/cirno-document/references/README.md"
    stamp = next(Path(source) for source, destination in artifacts.items() if destination == "cirno/_build_commit.txt")
    assert len(stamp.read_text().strip()) == 40
    assert not stamp.is_relative_to(core)
    assert sorted(path.name for path in core.iterdir()) == ["__init__.py"]
