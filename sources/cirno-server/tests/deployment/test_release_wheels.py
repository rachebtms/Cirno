"""Install the real release wheels and serve their bundled Web UI outside the checkout."""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import venv
from pathlib import Path

import httpx


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_release_wheels_start_with_owned_resources(tmp_path: Path):
    repository = Path(__file__).resolve().parents[4]
    bundle = Path(os.environ.get("CIRNO_TEST_WEBUI_DIST", repository / "build/webui"))
    assert (bundle / "index.html").is_file(), "Build the Web UI before release checks"
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    for name in ("pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(repository / name, checkout / name)
    for name in ("cirno-memory", "cirno-usage", "cirno-vault", "cirno-core", "cirno-server", "cirno"):
        shutil.copytree(repository / "sources" / name, checkout / "sources" / name,
                        ignore=shutil.ignore_patterns("tests", "__pycache__", ".pytest_cache", ".ruff_cache", ".DS_Store", "dist"))
    shutil.copytree(repository / "documents", checkout / "documents")
    shutil.copytree(bundle, checkout / "build/webui")
    wheels = tmp_path / "wheels"
    env = {**os.environ, "CIRNO_SKIP_WEBUI_BUILD": "1"}
    env.pop("PYTHONPATH", None)
    for source in (*(checkout / "sources" / name for name in ("cirno-memory", "cirno-usage", "cirno-vault", "cirno-core", "cirno-server")), checkout):
        subprocess.run([sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(wheels)],
                       cwd=source, env=env, check=True, capture_output=True, timeout=60)
    installation = tmp_path / "installation"
    # Reuse installed third-party dependencies; Cirno itself must resolve from these wheels.
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(installation)
    python = installation / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps", "--force-reinstall",
                    *map(str, wheels.glob("*.whl"))], cwd=tmp_path, env=env,
                   check=True, capture_output=True, timeout=60)
    probe = subprocess.run([str(python), "-I", "-c", "\n".join([
        "import cirno_memory, cirno_usage, cirno_vault, json, sys, tempfile",
        "from cirno_memory.repository import MemoryRepository",
        "from pathlib import Path",
        "from cirno_usage.store import LLMUsageStore",
        "from cirno_vault.vault import CredentialVault",
        "directory = Path(tempfile.mkdtemp())",
        "repository = MemoryRepository(directory / 'home')",
        "memory = repository.save('calibration seed 42', source='test', session_key='unit')",
        "assert repository.search('calibration', session_key='unit')['memories'][0]['id'] == memory['id']",
        "vault = CredentialVault(directory / 'credentials')",
        "record = vault.save(label='test', value='secret')",
        "assert vault.reveal(record['id'])['value'] == 'secret'",
        "store = LLMUsageStore(directory / 'usage.sqlite3')",
        "assert store.recent_calls() == []",
        "store.close()",
        "assert not any(name == 'cirno_core' or name.startswith('cirno_core.') for name in sys.modules)",
        "import cirno, cirno_core, cirno_server",
        "from cirno_server.webui.build import default_webui_dist_dir",
        "from cirno_core.agent.tools.mcp.provider import MCPProvider",
        "print(json.dumps({'packages': [m.__file__ for m in (cirno, cirno_core, cirno_server, cirno_memory, cirno_usage, cirno_vault)], 'assets': str(default_webui_dist_dir())}))",
    ])], cwd=tmp_path, env=env, check=True, capture_output=True, text=True, timeout=15)
    paths = json.loads(probe.stdout)
    assert all(Path(path).is_relative_to(installation) for path in paths["packages"])
    assert Path(paths["assets"]).is_relative_to(installation)
    assert (Path(paths["assets"]) / "index.html").is_file()
    port = free_port()
    health_port = free_port()
    config = tmp_path / "instance/config.json"
    config.parent.mkdir()
    config.write_text(json.dumps({
        "channels": {"websocket": {"host": "127.0.0.1", "port": port}},
        "server": {"healthHost": "127.0.0.1", "healthPort": health_port},
    }))
    log_path = tmp_path / "installed-service.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen([str(python), "-I", "-m", "cirno", "--config", str(config)],
                                   cwd=tmp_path, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 30
        with httpx.Client(trust_env=False, timeout=1) as client:
            while True:
                assert process.poll() is None, log_path.read_text()
                try:
                    response = client.get(f"http://127.0.0.1:{port}/")
                    if response.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                assert time.monotonic() < deadline, log_path.read_text()
                time.sleep(0.1)
            assert 'type="module"' in response.text
            assert client.get(f"http://127.0.0.1:{health_port}/v0/health").status_code == 200
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            raise
    assert process.returncode == 0, log_path.read_text()
