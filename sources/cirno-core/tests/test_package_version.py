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
        source = {str(Path.cwd() / 'sources/cirno-core/__init__.py')!r}
        spec = importlib.util.spec_from_file_location("cirno", source)
        package = importlib.util.module_from_spec(spec)
        sys.modules["cirno"] = package
        spec.loader.exec_module(package)
        fake = types.ModuleType("cirno.sdk.assistant")
        fake.Cirno = object
        fake.RunResult = object
        sys.modules["cirno.sdk.assistant"] = fake

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
