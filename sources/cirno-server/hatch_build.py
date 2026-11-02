"""Hatch build hook that bundles the Cirno server and Web UI.

Triggered automatically by `python -m build` (and any other hatch-driven build)
so published wheels and sdists ship a fresh webui without requiring developers
to remember `npm --prefix sources/cirno-web run build` beforehand. The core distribution owns the documentation Skill; this hook owns the browser bundle.

WebUI behavior:

- Skips for editable installs (`pip install -e .`). Editable mode is for Python
  development; webui contributors use `npm --prefix sources/cirno-web run dev` (Vite HMR) and
  do not need a packaged `dist/`.
- No-op when `sources/cirno-web/package.json` is absent (e.g. installing from an sdist that
  already contains a prebuilt `web/dist/`).
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
    # The bundle builder is stdlib-only apart from the small Bun helper.
    name = "_cirno_webui_build"
    spec = importlib.util.spec_from_file_location(name, _PROJECT_ROOT / "webui/build.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class WebUIBuildHook(BuildHookInterface):
    PLUGIN_NAME = "webui-build"

    def initialize(self, version: str, build_data: dict) -> None:  # noqa: D401
        root = Path(self.root)
        if self.target_name == "wheel" and version != "editable":
            for source in root.rglob("*"):
                relative = source.relative_to(root)
                if (not source.is_file() or any(part in {"tests", "__pycache__", "dist", ".pytest_cache", ".ruff_cache"} for part in relative.parts)
                        or source.suffix in {".pyc", ".pyo"} or relative.as_posix() in {"pyproject.toml", "hatch_build.py", "LICENSE", "THIRD_PARTY_NOTICES.md"}):
                    continue
                build_data.setdefault("force_include", {})[str(source)] = f"cirno_server/{relative.as_posix()}"
        webui_dir = root.parent / "cirno-web"
        package_json = webui_dir / "package.json"
        dist_dir = root.parents[1] / "build" / "webui"
        index_html = dist_dir / "index.html"
        package_target = "cirno_server" if self.target_name == "wheel" else "."

        # `pip install -e .` builds an editable wheel; skip the (slow) webui
        # bundle since editable installs target Python development and webui
        # work uses `bun run dev` instead.
        if self.target_name == "wheel" and version == "editable":
            from editables import EditableProject
            self._editable_directory = tempfile.TemporaryDirectory(prefix="cirno-editable-")
            editable = EditableProject("cirno-server", self.root)
            editable.map("cirno_server", root)
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

        if not package_json.is_file() and not index_html.is_file():
            # Container builds stage build/webui without frontend sources. Only
            # fall back to the in-package bundle when no staged build exists.
            dist_dir = root / "web/dist"
            index_html = dist_dir / "index.html"
        if dist_dir.is_dir():
            build_data.setdefault("force_include", {})[str(dist_dir)] = f"{package_target}/web/dist"

        if os.environ.get("CIRNO_SKIP_WEBUI_BUILD") == "1":
            self.app.display_info("[webui-build] skipped via CIRNO_SKIP_WEBUI_BUILD=1")
            return

        if not package_json.is_file():
            self.app.display_info(
                "[webui-build] no frontend source tree, assuming prebuilt cirno_server/web/dist/"
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
