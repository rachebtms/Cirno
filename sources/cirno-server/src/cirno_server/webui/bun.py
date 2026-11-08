"""A private Bun lifecycle-script environment shared by package and source builds."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def bun_environment(executable: str) -> Generator[dict[str, str]]:
    """Run lifecycle scripts' `node` commands with Bun, without a global Node shim."""
    env = os.environ.copy()
    runtime = Path(shutil.which(executable) or executable).resolve()
    if os.name == "nt" and runtime.suffix.lower() in {".cmd", ".bat"}:
        runtime = Path(subprocess.check_output(
            [str(runtime), "-p", "process.execPath"], text=True, timeout=10,
        ).strip())
    # `bun --bun install` does not alias node in dependency lifecycle scripts.
    # Only this subprocess tree sees the alias; Windows hardlinks need no admin rights.
    with tempfile.TemporaryDirectory(prefix="cirno-bun-") as temporary:
        node = Path(temporary) / ("node.exe" if os.name == "nt" else "node")
        try:
            node.hardlink_to(runtime)
        except OSError:
            shutil.copy2(runtime, node)
        env["PATH"] = os.pathsep.join((temporary, str(runtime.parent), env.get("PATH", "")))
        yield env
