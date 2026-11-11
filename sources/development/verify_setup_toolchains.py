"""Offline installation and protocol checks for ordinary CLI/MCP/Skill workflows."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path


def run(*arguments):
    return subprocess.run(arguments, check=True, capture_output=True, text=True, timeout=90).stdout


async def verify(root: Path) -> None:
    # A real local wheel exercises uv's normal console-script installation and
    # uvx's isolated tool environment without depending on a package registry.
    wheel = root / "cirno_cli_probe-0.0.1-py3-none-any.whl"
    metadata = "cirno_cli_probe-0.0.1.dist-info"
    entries = {
        "cirno_cli_probe.py": "def main():\n    print('standard-python-cli-ok')\n",
        f"{metadata}/METADATA": "Metadata-Version: 2.1\nName: cirno-cli-probe\nVersion: 0.0.1\n",
        f"{metadata}/WHEEL": "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{metadata}/entry_points.txt": "[console_scripts]\ncirno-cli-probe = cirno_cli_probe:main\n",
    }
    record = f"{metadata}/RECORD"
    entries[record] = "".join(f"{name},,\n" for name in [*entries, record])
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    python = str(Path(os.environ["CIRNO_SHELL_VENV"]) / "bin/python")
    run("uv", "pip", "install", "--python", python, "--no-index", "--no-deps", str(wheel))
    assert run("cirno-cli-probe").strip() == "standard-python-cli-ok"
    assert run("uvx", "--offline", "--from", str(wheel), "cirno-cli-probe").strip() == "standard-python-cli-ok"
    run("uv", "pip", "uninstall", "--python", python, "cirno-cli-probe")
    assert not (Path(python).parent / "cirno-cli-probe").exists()

    package = root / "npm-probe"
    package.mkdir()
    (package / "package.json").write_text(json.dumps({"name": "cirno-js-probe", "version": "0.0.1", "bin": {"cirno-js-probe": "probe.js"}}))
    (package / "probe.js").write_text("#!/usr/bin/env node\nconsole.log('standard-node-cli-ok');\n")
    run("npm", "install", "--global", "--install-links", "--ignore-scripts", "--no-audit", "--no-fund", str(package))
    assert run("cirno-js-probe").strip() == "standard-node-cli-ok"
    assert run("npx", "--offline", "--yes", "cirno-js-probe").strip() == "standard-node-cli-ok"
    run("npm", "uninstall", "--global", "cirno-js-probe")

    server = root / "mcp.js"
    server.write_text('''const rl = require("node:readline").createInterface({input: process.stdin});
rl.on("line", line => {
  const m = JSON.parse(line); if (m.id === undefined) return;
  let result;
  if (m.method === "initialize") result = {protocolVersion: m.params.protocolVersion, capabilities: {tools: {}}, serverInfo: {name: "minimal-probe", version: "1"}};
  else if (m.method === "tools/list") result = {tools: [{name: "echo", description: "Offline protocol probe", inputSchema: {type: "object", properties: {text: {type: "string"}}, required: ["text"]}}]};
  else if (m.method === "tools/call") result = {content: [{type: "text", text: m.params.arguments.text}]};
  else {console.log(JSON.stringify({jsonrpc: "2.0", id: m.id, error: {code: -32601, message: "Unsupported probe method"}})); return;}
  console.log(JSON.stringify({jsonrpc: "2.0", id: m.id, result}));
});
''')
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async with stdio_client(StdioServerParameters(command="node", args=[str(server)])) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            assert (await session.list_tools()).tools[0].name == "echo"
            result = await session.call_tool("echo", {"text": "standard-mcp-ok"})
            assert result.content[0].text == "standard-mcp-ok"

    from cirno_core.config.home import get_home_path, get_selected_instance_path, set_instance_path
    from cirno_core.skills.loader import SkillsLoader

    previous = get_selected_instance_path()
    set_instance_path(root / "skill-instance")
    try:
        directory = get_home_path() / "skills/minimal-probe"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text("---\nname: minimal-probe\ndescription: Offline skill installation check\n---\nUse the standard CLI tools.\n")
        loader = SkillsLoader(root)
        assert any(item["name"] == "minimal-probe" for item in loader.list_skills())
        assert "standard CLI tools" in loader.load_skill("minimal-probe")
    finally:
        set_instance_path(previous)
    print("OK standard uv/uvx and npm/npx install/run/uninstall, Node MCP stdio handshake/tool call and user Skill discovery/read", flush=True)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temporary:
        asyncio.run(verify(Path(temporary)))
