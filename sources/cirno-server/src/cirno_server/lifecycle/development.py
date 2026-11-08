"""Keep an owned development UI process tied to service lifetime."""

import asyncio

from cirno_server.webui.dev import WebUIDevServer


async def watch_dev_server(
    server: WebUIDevServer,
    shutdown_event: asyncio.Event,
    *,
    poll_interval_s: float = 0.2,
) -> None:
    """Fail the foreground service when its owned Vite sidecar exits."""
    while not shutdown_event.is_set():
        await asyncio.sleep(poll_interval_s)
        if shutdown_event.is_set():
            return
        server.ensure_running()
