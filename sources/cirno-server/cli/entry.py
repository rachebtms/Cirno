"""Cirno console entrypoint."""

import os
import sys


def main() -> None:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if callable(reconfigure := getattr(stream, "reconfigure", None)):
                reconfigure(encoding="utf-8", errors="replace")
    if os.name != "nt":
        from cirno_server.cli.process_identity import _set_process_title
        _set_process_title("cirno")
    from cirno_core.utils.rotating_output import configure_background_output_from_env
    configure_background_output_from_env()
    from cirno_server.cli.commands import app
    app()
