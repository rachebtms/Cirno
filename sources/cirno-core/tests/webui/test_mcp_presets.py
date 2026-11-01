from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from cirno.webui.mcp.presets import _parse_presets


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


@pytest.mark.parametrize("target", ["wheel", "sdist"])
def test_distributions_bundle_webui_and_channel_resources(tmp_path: Path, target: str) -> None:
    core = Path(__file__).resolve().parents[2]
    repository = core.parent.parent
    for name in ("pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(repository / name, tmp_path / name)
    package = tmp_path / "sources/cirno-core"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    resources = {
        "webui/mcp/presets.json": (core / "webui/mcp/presets.json").read_bytes(),
        "agent/tools/names.json": (core / "agent/tools/names.json").read_bytes(),
        "cli/assets/dock-icon.png": (core / "cli/assets/dock-icon.png").read_bytes(),
        "web/dist/index.html": b"<!DOCTYPE html><html>Cirno</html>",
    }
    for name, content in resources.items():
        destination = package / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    for name in ("tests/test_root.py", "channels/tests/test_shared.py", "channels/telegram/tests/test_channel.py"):
        destination = package / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("raise RuntimeError('test source must not ship')", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", f"import hatchling.build; hatchling.build.build_{target}('dist')"],
        cwd=tmp_path, env={**os.environ, "HATCH_BUILD_NO_HOOKS": "1"},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    if target == "wheel":
        with ZipFile(next((tmp_path / "dist").glob("*.whl"))) as wheel:
            assert not any("/tests/" in name for name in wheel.namelist())
            for name, content in resources.items():
                assert wheel.read("cirno/" + name) == content
    else:
        with tarfile.open(next((tmp_path / "dist").glob("*.tar.gz"))) as sdist:
            assert not any("/tests/" in name for name in sdist.getnames())
            for name, content in resources.items():
                member = next(member for member in sdist.getnames() if member.endswith("/sources/cirno-core/" + name))
                with sdist.extractfile(member) as bundled:
                    assert bundled.read() == content
