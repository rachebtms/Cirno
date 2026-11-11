from __future__ import annotations

import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path


def test_source_checkout_import_uses_pyproject_version_without_metadata() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    expected = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    script = textwrap.dedent(
        f"""
        import sys
        import types

        import importlib.util
        source = {str(Path.cwd() / 'sources/cirno/src/cirno/__init__.py')!r}
        spec = importlib.util.spec_from_file_location("cirno", source)
        package = importlib.util.module_from_spec(spec)
        sys.modules["cirno"] = package
        spec.loader.exec_module(package)
        fake = types.ModuleType("cirno_core.sdk.assistant")
        fake.Cirno = object
        fake.RunResult = object
        sys.modules["cirno_core.sdk.assistant"] = fake

        import cirno

        print(cirno.__version__)
        """
    )

    proc = subprocess.run(
        [sys.executable, "-S", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == expected


def test_workspace_packages_and_frontend_lockfile_share_one_version() -> None:
    import json

    root = Path(__file__).resolve().parents[3]
    manifests = [tomllib.loads((root / name).read_text())["project"] for name in (
        "pyproject.toml", "sources/cirno-setup/pyproject.toml", "sources/cirno-memory/pyproject.toml", "sources/cirno-usage/pyproject.toml", "sources/cirno-vault/pyproject.toml",
        "sources/cirno-core/pyproject.toml", "sources/cirno-server/pyproject.toml",
    )]
    expected = manifests[0]["version"]
    for project in manifests:
        assert project["version"] == expected
        dependencies = [*project.get("dependencies", []), *(
            dependency for group in project.get("optional-dependencies", {}).values() for dependency in group
        )]
        for dependency in dependencies:
            if dependency.startswith("cirno-"):
                assert dependency.partition("==")[2] == expected, dependency
    frontend = json.loads((root / "sources/cirno-web/package.json").read_text())
    lock = json.loads((root / "sources/cirno-web/package-lock.json").read_text())
    assert frontend["version"] == lock["version"] == lock["packages"][""]["version"] == expected
