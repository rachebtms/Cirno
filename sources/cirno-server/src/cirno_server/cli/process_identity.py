"""Give the single Cirno service a recognizable operating-system name."""

import os
import sys


def set_process_title(title: str) -> None:
    if sys.platform == "linux":
        os.environ.setdefault("SPT_NOENV", "1")
    from setproctitle import setproctitle

    setproctitle(title)
