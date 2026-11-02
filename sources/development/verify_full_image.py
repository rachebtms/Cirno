"""Exercise the full image's commands and bundled embedding without credentials."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

COMMANDS = (
    "git", "git-lfs", "gh", "tea", "go", "curl", "wget", "ssh", "scp", "sftp", "rsync", "rclone",
    "tmux", "rg", "fd", "fzf", "bat", "jq", "yq", "tree", "python3", "pipx", "uv", "uvx", "hf",
    "node", "npm", "npx", "bun", "summarize", "mcporter", "gog", "xurl", "ffmpeg", "yt-dlp",
    "pandoc", "pdftotext", "tesseract", "sqlite3", "brew",
)


def main() -> None:
    assert os.getuid() == 1000, "Full image tools must work as the non-root Cirno user"
    for name in COMMANDS:
        assert shutil.which(name), f"Missing command: {name}"
    commands = [
        ["git", "--version"], ["git-lfs", "version"], ["gh", "--version"], ["tea", "--version"],
        ["go", "version"], ["curl", "--version"], ["wget", "--version"], ["ssh", "-V"],
        ["rsync", "--version"], ["rclone", "version"], ["tmux", "-V"], ["rg", "--version"],
        ["fd", "--version"], ["fzf", "--version"], ["bat", "--version"], ["jq", "--version"],
        ["yq", "--version"], ["tree", "--version"], ["python3", "--version"], ["pipx", "--version"],
        ["uv", "--version"], ["uvx", "--version"], ["hf", "--help"], ["node", "--version"],
        ["npm", "--version"], ["npx", "--version"], ["bun", "--version"], ["summarize", "--version"],
        ["mcporter", "--version"], ["gog", "--version"], ["xurl", "--help"], ["ffmpeg", "-version"],
        ["yt-dlp", "--version"], ["pandoc", "--version"], ["pdftotext", "-v"], ["tesseract", "--version"],
        ["sqlite3", "--version"], ["brew", "--version"], ["bash", "-c", "nvm --version"],
    ]
    for command in commands:
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        assert result.returncode == 0, f"{command}: {result.stdout}\n{result.stderr}"
        print(f"OK {' '.join(command)}", flush=True)
    from cirno_core.config.loader import load_config
    from cirno_server.channels.telegram.manifest import PLUGIN
    from cirno_server.features.service import extra_installed
    import cirno_core.memory.embedding_worker as worker

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


if __name__ == "__main__":
    main()
