"""A copyable invocation of the installed local trigger sender."""

import os
import shlex
import subprocess
import sys
from pathlib import Path


def invocation(store: Path, trigger_id: str, message: str = "message") -> str:
    arguments = [sys.executable, "-m", "cirno_core.triggers", "--store", str(store.resolve()), trigger_id, message]
    return subprocess.list2cmdline(arguments) if os.name == "nt" else shlex.join(arguments)
