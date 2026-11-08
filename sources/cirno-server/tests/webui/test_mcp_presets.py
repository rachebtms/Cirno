from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
from cirno_server.webui.mcp.presets import _parse_presets
from pydantic import ValidationError


@pytest.fixture
def preset_data() -> dict:
    return {
        "name": "example",
        "display_name": "Example",
        "category": "docs",
        "description": "Search example documentation.",
        "docs_url": "https://example.com/docs",
        "transport": "streamableHttp",
        "install_supported": True,
        "brand_domain": "example.com",
        "brand_color": "#111827",
        "server": {"type": "streamableHttp", "url": "https://example.com/mcp"},
        "fields": [{"name": "api_key", "label": "API key", "target": ["header", "Authorization"]}],
    }


def test_json_presets_keep_credential_and_tool_defaults(preset_data: dict) -> None:
    preset, = _parse_presets(json.dumps([preset_data]))

    assert preset.fields[0].secret is True
    assert preset.fields[0].required is True
    assert preset.fields[0].target == ("header", "Authorization")
    assert preset.server is not None
    assert preset.server.enabled_tools == ["*"]


def test_json_presets_reject_duplicate_names(preset_data: dict) -> None:
    with pytest.raises(ValueError, match="Duplicate MCP preset name: example"):
        _parse_presets(json.dumps([preset_data, preset_data]))


@pytest.mark.parametrize("invalid_part", ["field_target", "server_key", "boolean"])
def test_json_presets_reject_invalid_configuration(preset_data: dict, invalid_part: str) -> None:
    if invalid_part == "field_target":
        preset_data["fields"][0]["target"] = ["query", "Authorization"]
    elif invalid_part == "server_key":
        preset_data["server"]["tool_timout"] = 60
    else:
        preset_data["fields"][0]["secret"] = "false"

    with pytest.raises(ValidationError):
        _parse_presets(json.dumps([preset_data]))


@pytest.mark.parametrize("owner,resource", [
    ("core", "agent/tools/names.json"),
    ("server", "webui/mcp/presets.json"),
    ("server", "cli/assets/dock-icon.png"),
])
def test_owned_resources_survive_regular_wheel_build(tmp_path, owner, resource):
    package = Path(__file__).resolve().parents[3] / f"cirno-{owner}"
    source = tmp_path / "sources" / f"cirno-{owner}"
    source.mkdir(parents=True)
    for file in ("pyproject.toml", "hatch_build.py", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(package / file, source / file)
    content = (package / "src" / f"cirno_{owner}" / resource).read_bytes()
    module_root = source / "src" / f"cirno_{owner}"
    target = module_root / resource
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    (module_root / "__init__.py").write_text("")
    result = subprocess.run([sys.executable, "-c", "import hatchling.build; hatchling.build.build_wheel('dist')"],
                            cwd=source, env={**os.environ, "CIRNO_SKIP_WEBUI_BUILD": "1"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    with ZipFile(next((source / "dist").glob("*.whl"))) as wheel:
        assert wheel.read(f"cirno_{owner}/" + resource) == content
