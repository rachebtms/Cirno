"""Bundle the Web UI in release wheels and source distributions."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

PROJECT = Path(__file__).resolve().parent


def _load_webui_build_module() -> ModuleType:
    name = "_cirno_webui_build"
    directory = PROJECT / "src/cirno_server/webui"
    spec = importlib.util.spec_from_file_location(name, directory / "build.py", submodule_search_locations=[str(directory)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class WebUIBuildHook(BuildHookInterface):
    PLUGIN_NAME = "webui-build"

    def initialize(self, version: str, build_data: dict) -> None:
        if version == "editable":
            return
        root = Path(self.root)
        source = root.parent / "cirno-web"
        dist = root.parents[1] / "build/webui"
        source_available = (source / "package.json").is_file()
        packaged = root / "src/cirno_server/web/dist"
        if not source_available and ((packaged / "index.html").is_file() or not (dist / "index.html").is_file()):
            dist = packaged
        if source_available and os.environ.get("CIRNO_SKIP_WEBUI_BUILD") != "1":
            builder = _load_webui_build_module()
            builder.build_webui_bundle(
                source_dir=source, dist_dir=dist, output=self.app.display_info,
                force=os.environ.get("CIRNO_FORCE_WEBUI_BUILD") == "1",
            )
            if not (dist / "index.html").is_file():
                raise RuntimeError(f"Web UI build did not create {dist / 'index.html'}")
        if dist.is_dir():
            target = "cirno_server" if self.target_name == "wheel" else "src/cirno_server"
            build_data.setdefault("force_include", {})[str(dist)] = f"{target}/web/dist"
