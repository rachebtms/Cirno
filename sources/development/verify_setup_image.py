"""Exercise the selected research preset's commands and bundled embedding without credentials."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

COMMANDS = (
    "git", "git-lfs", "gh", "tea", "curl", "wget", "ssh", "scp", "sftp", "rsync", "rclone",
    "tmux", "rg", "fd", "fzf", "bat", "jq", "yq", "tree", "python3", "uv", "uvx",
    "node", "npm", "npx", "summarize", "mcporter", "gog", "xurl", "ffmpeg", "yt-dlp",
    "pandoc", "pdftotext", "tesseract", "sqlite3", "brew",
    "soffice", "latex", "pdflatex", "bibtex", "latexmk", "chromium", "playwright", "pytest", "fc-list",
)


def check_python_packages() -> None:
    from cirno_core.processes.environment import ExecutionEnvironment

    imports = "import docx, openpyxl, pptx, pypdf, pdfplumber, reportlab, lxml.etree, debugpy, pytest, numpy, PIL, matplotlib, pymupdf, fitz, playwright"
    command = shlex.join(["python", "-c", imports])
    for args in (["python", "-c", imports], ["python3", "-c", imports],
                 ["bash", "-c", command], ["bash", "-lc", command]):
        result = subprocess.run(args, env=ExecutionEnvironment().build(), capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
    print("OK bundled Python document, PDF, XML and debugging libraries", flush=True)


def check_persistence() -> None:
    check_python_packages()
    result = subprocess.run(["python", "-c", "import cirno_persistence_probe; assert cirno_persistence_probe.value == 'survives-recreation'"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(["tea", "logins", "list"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and "ci-persistence" in result.stdout, result.stdout + result.stderr
    result = subprocess.run(["cirno-npm-probe"], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.strip() == "survives-recreation", result.stderr
    print("OK persistent Python/npm packages and Gitea login configuration", flush=True)


def prepare_persistence() -> None:
    # A local wheel keeps this check independent of PyPI and external accounts.
    with tempfile.TemporaryDirectory() as temporary:
        wheel = Path(temporary) / "cirno_persistence_probe-0.0.1-py3-none-any.whl"
        dist = "cirno_persistence_probe-0.0.1.dist-info"
        files = {
            "cirno_persistence_probe.py": "value = 'survives-recreation'\n",
            f"{dist}/METADATA": "Metadata-Version: 2.1\nName: cirno-persistence-probe\nVersion: 0.0.1\n",
            f"{dist}/WHEEL": "Wheel-Version: 1.0\nGenerator: cirno-smoke\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        }
        files[f"{dist}/RECORD"] = "".join(f"{name},,\n" for name in [*files, f"{dist}/RECORD"])
        with zipfile.ZipFile(wheel, "w") as archive:
            for name, contents in files.items():
                archive.writestr(name, contents)
        from cirno_setup.python import package_command

        subprocess.run(package_command("install", shutil.which("python"), ["--no-index", "--no-deps", str(wheel)]), check=True)
        package = Path(temporary) / "npm-probe"
        package.mkdir()
        (package / "package.json").write_text(json.dumps({
            "name": "cirno-npm-probe", "version": "0.0.1", "bin": {"cirno-npm-probe": "probe.js"},
        }))
        (package / "probe.js").write_text("#!/usr/bin/env node\nconsole.log('survives-recreation');\n")
        subprocess.run(["npm", "install", "--global", "--install-strategy=hoisted", "--install-links", "--ignore-scripts", "--no-audit", "--no-fund", str(package)], check=True)
    config = Path(os.environ["XDG_CONFIG_HOME"]) / "tea" / "config.yml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("logins:\n  - name: ci-persistence\n    url: https://gitea.invalid\n    user: ci-owner\n    token: fixture-only\n    default: true\n")
    config.chmod(0o600)
    import importlib.util
    assert importlib.util.find_spec("cirno_persistence_probe") is None, "User pip packages must not replace Cirno's environment"
    check_persistence()


def main() -> None:
    assert os.getuid() == 1000, "Selected tools must work as the non-root Cirno user"
    for name in COMMANDS:
        assert shutil.which(name), f"Missing command: {name}"
    # Embedding SDK dependencies may expose their own hf entry point; the
    # standalone Hugging Face CLI is not selected as an additional component.
    for name in ("go", "pipx", "bun", "manim"):
        assert shutil.which(name) is None, f"Unbundled command remains in the default image: {name}"
    commands = [
        ["git", "--version"], ["git-lfs", "version"], ["gh", "--version"], ["tea", "--version"],
        ["curl", "--version"], ["wget", "--version"], ["ssh", "-V"],
        ["rsync", "--version"], ["rclone", "version"], ["tmux", "-V"], ["rg", "--version"],
        ["fd", "--version"], ["fzf", "--version"], ["bat", "--version"], ["jq", "--version"],
        ["yq", "--version"], ["tree", "--version"], ["python3", "--version"],
        ["uv", "--version"], ["uvx", "--version"], ["node", "--version"],
        ["npm", "--version"], ["npx", "--version"], ["summarize", "--version"],
        ["mcporter", "--version"], ["gog", "--version"], ["xurl", "--help"], ["ffmpeg", "-version"],
        ["yt-dlp", "--version"], ["pandoc", "--version"], ["pdftotext", "-v"], ["tesseract", "--version"],
        ["sqlite3", "--version"], ["brew", "--version"], ["bash", "-c", "nvm --version"],
        ["soffice", "--version"], ["latex", "--version"], ["latexmk", "-v"],
        ["chromium", "--version"], ["playwright", "--version"], ["pytest", "--version"],
    ]
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        assert result.returncode == 0, f"{command}: {result.stdout}\n{result.stderr}"
        print(f"OK {' '.join(command)}", flush=True)
    from cirno_core.processes.environment import ExecutionEnvironment
    subprocess.run(["python", str(Path(__file__).with_name("verify_setup_media.py"))],
                   env=ExecutionEnvironment().build(), check=True, timeout=360)
    import cirno_memory.embedding_worker as worker
    from cirno_core.config.loader import load_config
    from cirno_server.channels.telegram.manifest import PLUGIN
    from cirno_server.features.service import extra_installed

    assert extra_installed("telegram", list(PLUGIN.dependencies)), "Telegram dependencies are incomplete"
    memory = load_config().agents.defaults.memory
    assert not memory.embedding_enabled, "Bundled embeddings must remain disabled by default"
    assert Path(memory.embedding_model_path).is_file()
    assert Path(memory.embedding_tokenizer_path).is_file()
    result = subprocess.run(
        [sys.executable, worker.__file__, memory.embedding_model_path, memory.embedding_tokenizer_path],
        input=json.dumps({"texts": ["长期科研任务的记忆检索"]}) + "\n", capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output = json.loads(result.stdout)
    assert len(output["vectors"][0]) == 512, output
    print(f'OK bundled BGE-small INT8 inference: {output["peak_mb"]:.1f} MB peak', flush=True)
    prepare_persistence()


def check_base() -> None:
    assert os.getuid() == 1000
    for name in ("cirno", "cirno-setup", "python", "uv", "git", "ssh", "node", "npm", "npx"):
        assert shutil.which(name), name
    for name in ("soffice", "pdflatex", "tea", "pytest", "chromium"):
        assert shutil.which(name) is None, f"Optional command leaked into the base image: {name}"
    from cirno_core.processes.environment import ExecutionEnvironment
    subprocess.run(["python", "-c", "import sys, pip; print(sys.version); print(pip.__version__)"], env=ExecutionEnvironment().build(), check=True)
    print("OK unified base without optional tools", flush=True)


if __name__ == "__main__":
    if "--base" in sys.argv:
        check_base()
    elif "--check-persistence" in sys.argv:
        check_persistence()
    else:
        main()
