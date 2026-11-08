"""Bundle the engine's source revision and built-in documentation Skill."""

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CoreBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:
        if version == "editable":
            return
        root = Path(self.root)
        package = root / "src/cirno_core"
        checkout = root.parents[1]
        target = "cirno_core" if self.target_name == "wheel" else "src/cirno_core"
        stamp = package / "_build_commit.txt"
        commit = (subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
                  if (checkout / ".git").exists() else stamp.read_text().strip() if stamp.is_file() else None)
        if commit:
            self._build_directory = TemporaryDirectory(prefix="cirno-core-build-")
            generated = Path(self._build_directory.name) / "_build_commit.txt"
            generated.write_text(commit + "\n", encoding="utf-8")
            build_data.setdefault("force_include", {})[str(generated)] = f"{target}/_build_commit.txt"
        docs = checkout / "documents"
        if docs.is_dir() and root.parent.name == "sources":
            build_data.setdefault("force_include", {})[str(docs)] = f"{target}/skills/builtin/cirno-document/references"
