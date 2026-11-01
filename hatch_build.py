"""Hatch build hook that bundles the WebUI and cirno skill documentation.

Triggered automatically by `python -m build` (and any other hatch-driven build)
so published wheels and sdists ship a fresh webui without requiring developers
to remember `npm --prefix sources/cirno-web run build` beforehand. Markdown guides and JSON examples from documents/ are
embedded into the cirno-document skill in release artifacts; editable installs read documents/ directly.

WebUI behavior:

- Skips for editable installs (`pip install -e .`). Editable mode is for Python
  development; webui contributors use `npm --prefix sources/cirno-web run dev` (Vite HMR) and
  do not need a packaged `dist/`.
- No-op when `sources/cirno-web/package.json` is absent (e.g. installing from an sdist that
  already contains a prebuilt `sources/cirno-core/web/dist/`).
- Skips when `CIRNO_SKIP_WEBUI_BUILD=1` is set.
- Reuses `build/webui/` only when it is already fresh, unless
  `CIRNO_FORCE_WEBUI_BUILD=1` is set.
- Uses `npm` when available, otherwise uses an installed Bun.
  Bun builds use `--bun` so Node is not required.
"""

from __future__ import annotations

import os
import tempfile
import sys
from pathlib import Path
from types import ModuleType

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _load_webui_build_module() -> ModuleType:
    import importlib.util
    for name, source in [("cirno", "__init__.py"), ("cirno.utils.bun", "utils/bun.py"), ("cirno.webui.build", "webui/build.py")]:
        spec = importlib.util.spec_from_file_location(name, _PROJECT_ROOT / "sources/cirno-core" / source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


class WebUIBuildHook(BuildHookInterface):
    PLUGIN_NAME = "webui-build"

    def initialize(self, version: str, build_data: dict) -> None:  # noqa: D401
        root = Path(self.root)
        docs_dir = root / "documents"
        if not (docs_dir / "README.md").is_file():
            raise RuntimeError("[cirno-document] documents/README.md is required to bundle documentation")
        # Editable installs read documents/ directly. Release artifacts embed the
        # same files without creating generated copies in the source package.
        package_target = "cirno" if self.target_name == "wheel" else "sources/cirno-core"
        if version != "editable" and self.target_name == "wheel":
            for source in docs_dir.rglob("*"):
                if not source.is_file() or source.suffix not in {".md", ".json"}:
                    continue
                relative = source.relative_to(docs_dir)
                if relative.parts[0] not in {"plans", "superpowers"}:
                    build_data.setdefault("force_include", {})[str(source)] = (
                        f"cirno/skills/builtin/cirno-document/references/{relative.as_posix()}"
                    )
        webui_dir = root / "sources" / "cirno-web"
        package_json = webui_dir / "package.json"
        dist_dir = root / "build" / "webui"
        index_html = dist_dir / "index.html"

        # `pip install -e .` builds an editable wheel; skip the (slow) webui
        # bundle since editable installs target Python development and webui
        # work uses `bun run dev` instead.
        if self.target_name == "wheel" and version == "editable":
            from editables import EditableProject
            self._editable_directory = tempfile.TemporaryDirectory(prefix="cirno-editable-")
            editable = EditableProject("cirno-ai", self.root)
            editable.map("cirno", root / "sources" / "cirno-core")
            for name, content in editable.files():
                generated = Path(self._editable_directory.name) / name
                generated.write_text(content, encoding="utf-8")
                build_data.setdefault("force_include", {})[str(generated)] = name
            build_data.setdefault("dependencies", []).extend(editable.dependencies())
            self.app.display_info(
                "[webui-build] skipped for editable install "
                "(use `npm --prefix sources/cirno-web run build` to bundle webui manually)"
            )
            return

        import subprocess
        commit = None
        if (root / ".git").exists():
            commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        else:
            stamp = root / "sources/cirno-core/_build_commit.txt"
            if stamp.is_file():
                commit = stamp.read_text(encoding="utf-8").strip()
        if commit:
            self._build_directory = tempfile.TemporaryDirectory(prefix="cirno-build-")
            commit_file = Path(self._build_directory.name) / "_build_commit.txt"
            commit_file.write_text(commit + "\n", encoding="utf-8")
            build_data.setdefault("force_include", {})[str(commit_file)] = f"{package_target}/_build_commit.txt"
        if not package_json.is_file() and not index_html.is_file():
            # Container builds stage build/webui without frontend sources. Only
            # fall back to the in-package bundle when no staged build exists.
            dist_dir = root / "sources/cirno-core/web/dist"
            index_html = dist_dir / "index.html"
        if dist_dir == root / "build" / "webui" and dist_dir.is_dir():
            build_data.setdefault("force_include", {})[str(dist_dir)] = f"{package_target}/web/dist"

        if os.environ.get("CIRNO_SKIP_WEBUI_BUILD") == "1":
            self.app.display_info("[webui-build] skipped via CIRNO_SKIP_WEBUI_BUILD=1")
            return

        if not package_json.is_file():
            self.app.display_info(
                "[webui-build] no frontend source tree, assuming prebuilt cirno/web/dist/"
            )
            return

        webui_build = _load_webui_build_module()
        status = webui_build.inspect_webui_bundle(source_dir=webui_dir, dist_dir=dist_dir)
        force = os.environ.get("CIRNO_FORCE_WEBUI_BUILD") == "1"
        if not status.needs_build and not force:
            self.app.display_info(
                f"[webui-build] reusing existing build at {dist_dir} "
                "(already fresh; set CIRNO_FORCE_WEBUI_BUILD=1 to rebuild)"
            )
            return

        if status.needs_build and not force:
            self.app.display_info(
                f"[webui-build] {webui_build.describe_webui_bundle_status(status)}"
            )

        try:
            webui_build.build_webui_bundle(
                source_dir=webui_dir,
                dist_dir=dist_dir,
                output=self.app.display_info,
            )
        except webui_build.WebUIBuildError as exc:
            raise RuntimeError(
                "[webui-build] "
                f"{exc}. Install `bun` or `npm`, or set CIRNO_SKIP_WEBUI_BUILD=1 to bypass."
            ) from exc

        if not index_html.is_file():
            raise RuntimeError(
                f"[webui-build] build finished but {index_html} is missing; "
                "check sources/cirno-web/vite.config.ts outDir."
            )
        build_data.setdefault("force_include", {})[str(dist_dir)] = f"{package_target}/web/dist"
        self.app.display_info(f"[webui-build] webui ready at {dist_dir}")
