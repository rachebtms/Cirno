"""Open the local Web UI after its listeners become reachable."""

import asyncio
from collections.abc import Callable
from contextlib import suppress

from cirno_server.cli.webui_support import _launch_browser, _webui_display_url


def http_endpoint_responding(url: str, *, timeout_s: float = 0.25) -> bool:
    """Return whether an HTTP endpoint responds, including with an auth error."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout_s):
            return True
    except urllib.error.HTTPError:
        return True
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return False



async def open_when_ready(
    url: str, *, ready_url: str | None, fallback_host: str, fallback_port: int,
    report: Callable[[str], None],
) -> None:
    """Wait for the service to bind, then point the user's browser at the webui."""
    if not url:
        return
    from urllib.parse import urlparse

    # Channels start asynchronously. When the caller supplies a backend
    # readiness route, wait for an actual HTTP response rather than probing
    # the WebSocket listener with an incomplete TCP connection.
    if ready_url:
        for _ in range(40):  # ~4s max per listener
            if await asyncio.to_thread(
                http_endpoint_responding,
                ready_url,
            ):
                break
            await asyncio.sleep(0.1)

    parsed = urlparse(url)
    target_host = parsed.hostname or fallback_host or "127.0.0.1"
    target_port = parsed.port or fallback_port
    for _ in range(40):  # ~4s max
        try:
            _reader, writer = await asyncio.open_connection(
                target_host,
                target_port,
            )
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
            break
        except OSError:
            await asyncio.sleep(0.1)
    display_url = _webui_display_url(url)
    try:
        if _launch_browser(url):
            report(f"[green]✓[/green] Opened browser at {display_url}")
        else:
            report(f"[yellow]Could not open browser; visit {display_url}[/yellow]")
    except Exception as e:
        report(f"[yellow]Could not open browser ({e}); visit {display_url}[/yellow]")
