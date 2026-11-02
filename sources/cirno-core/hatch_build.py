"""Build the flat engine package and its built-in documentation skill."""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CoreBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:
        root = Path(self.root)
        if self.target_name == "wheel" and version != "editable":
            for source in root.rglob("*"):
                relative = source.relative_to(root)
                if (not source.is_file() or any(part in {"tests", "__pycache__", "dist", ".pytest_cache", ".ruff_cache"} for part in relative.parts)
                        or source.suffix in {".pyc", ".pyo"} or relative.as_posix() in {"pyproject.toml", "hatch_build.py", "LICENSE", "THIRD_PARTY_NOTICES.md", "_build_commit.txt"}):
                    continue
                build_data.setdefault("force_include", {})[str(source)] = f"cirno_core/{relative.as_posix()}"
        if self.target_name == "wheel" and version == "editable":
            from editables import EditableProject
            self._editable_directory = TemporaryDirectory(prefix="cirno-core-editable-")
            editable = EditableProject("cirno-core", self.root)
            editable.map("cirno_core", root)
            for name, content in editable.files():
                generated = Path(self._editable_directory.name) / name
                generated.write_text(content, encoding="utf-8")
                build_data.setdefault("force_include", {})[str(generated)] = name
            build_data.setdefault("dependencies", []).extend(editable.dependencies())
            return
        if version != "editable":
            checkout = root.parents[1]
            stamp = root / "_build_commit.txt"
            commit = (subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
                      if (checkout / ".git").exists() else stamp.read_text().strip() if stamp.is_file() else None)
            if commit:
                self._build_directory = TemporaryDirectory(prefix="cirno-core-build-")
                generated = Path(self._build_directory.name) / "_build_commit.txt"
                generated.write_text(commit + "\n", encoding="utf-8")
                destination = "cirno_core/_build_commit.txt" if self.target_name == "wheel" else "_build_commit.txt"
                build_data.setdefault("force_include", {})[str(generated)] = destination
        docs = root.parents[1] / "documents"
        if docs.is_dir() and (root.parent.name == "sources") :
            target = "cirno_core" if self.target_name == "wheel" else "."
            build_data.setdefault("force_include", {})[str(docs)] = (
                f"{target}/skills/builtin/cirno-document/references"
            )
