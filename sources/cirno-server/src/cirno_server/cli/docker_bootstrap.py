"""Initialize a local Docker instance without replacing existing settings."""

import os
import sys
from pathlib import Path

from cirno_core import __version__
from cirno_core.config.loader import save_config
from cirno_core.config.schema import Config
from cirno_server.channels.websocket.config import WebSocketConfig
from filelock import FileLock


def initialize_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(path.parent / ".docker-bootstrap.lock"):
        if path.exists():
            print(f"[entrypoint] existing {path} found — leaving it in place")
            print("[entrypoint] Open the WebUI to sign in or complete setup")
            return

        web_token = os.environ.get("CIRNO_WEB_TOKEN") or ""
        websocket = WebSocketConfig(
            enabled=True, host="0.0.0.0", token_issue_secret=web_token,
            websocket_requires_token=True, browser_setup=not bool(web_token),
        )
        config = Config.model_validate({
            "lastRunVersion": __version__,
            "server": {"healthHost": "0.0.0.0"},
            "channels": {"websocket": websocket.model_dump(by_alias=True)},
        })
        save_config(config, path)
        print(f"[entrypoint] initialized {path}")
        print("[entrypoint] WebUI: http://localhost:8765 — complete setup in your browser")


if __name__ == "__main__":
    initialize_config(Path(sys.argv[1]))
