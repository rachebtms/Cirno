"""Release distributions must retain resources when rebuilt outside a checkout."""

import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest


@pytest.mark.parametrize("package", ["cirno-core", "cirno-server"])
def test_sdist_rebuild_preserves_package_resources(tmp_path: Path, package: str) -> None:
    repository = Path(__file__).resolve().parents[3]
    original = repository / "sources" / package
    source = tmp_path / "checkout" / "sources" / package
    source.mkdir(parents=True)
    for name in ("pyproject.toml", "hatch_build.py", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(original / name, source / name)
    namespace = package.replace("-", "_")
    module_root = source / "src" / namespace
    module_root.mkdir(parents=True)
    (module_root / "__init__.py").write_text('__version__ = "0.2.0"\n')
    if package == "cirno-core":
        (module_root / "_build_commit.txt").write_text("a" * 40 + "\n")
        required = {"cirno_core/_build_commit.txt": ("a" * 40 + "\n").encode()}
    else:
        bundle = module_root / "web" / "dist"
        (bundle / "assets").mkdir(parents=True)
        (bundle / "index.html").write_text('<html><script src="/assets/app.js"></script></html>')
        (bundle / "assets" / "app.js").write_text('console.log("Cirno");')
        required = {
            "cirno_server/web/dist/index.html": (bundle / "index.html").read_bytes(),
            "cirno_server/web/dist/assets/app.js": (bundle / "assets" / "app.js").read_bytes(),
        }
    env = {**os.environ, "CIRNO_SKIP_WEBUI_BUILD": "1"}
    sdists = tmp_path / "sdists"
    subprocess.run([sys.executable, "-m", "hatchling", "build", "-t", "sdist", "-d", str(sdists)],
                   cwd=source, env=env, check=True, capture_output=True, text=True, timeout=30)
    extracted = tmp_path / "extracted"
    with tarfile.open(next(sdists.glob("*.tar.gz"))) as archive:
        archive.extractall(extracted, filter="data")
    rebuilt = next(extracted.iterdir())
    wheels = tmp_path / "wheels"
    subprocess.run([sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(wheels)],
                   cwd=rebuilt, env=env, check=True, capture_output=True, text=True, timeout=30)
    with zipfile.ZipFile(next(wheels.glob("*.whl"))) as wheel:
        for name, content in required.items():
            assert wheel.namelist().count(name) == 1
            assert wheel.read(name) == content
