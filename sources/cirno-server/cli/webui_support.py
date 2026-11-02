"""Shared WebUI setup, URL, health, and browser helpers."""

import os
import sys
import webbrowser
from typing import TYPE_CHECKING, Any

import typer
from cirno_core.config.schema import Config
from cirno_core.security.network import is_loopback_host
from cirno_server.webui.build import (
    BuildMode,
    WebUIBuildError,
    ensure_webui_bundle,
    inspect_webui_bundle,
)
from rich.console import Console
from rich.markup import escape
from rich.text import Text

if TYPE_CHECKING:
    pass

__all__ = ['_gateway_health_bind_note', '_gateway_health_url', '_host_for_local_browser', '_launch_browser', '_launch_browser_command', '_launch_macos_browser', '_launch_unix_browser', '_prepare_webui_bundle_for_gateway', '_print_foreground_port_conflict', '_tcp_endpoint_reachable', '_use_wsl_browser', '_webui_browser_url', '_webui_channel_enabled', '_webui_config_dict', '_webui_display_url', '_webui_endpoint_reachable', 'webui_bootstrap_secret']

console = Console()

_TEXT_ONLY_BROWSERS = frozenset({"elinks", "links", "links2", "lynx", "w3m"})


def _launch_browser(url: str) -> bool:
    """Open *url* and request a foreground browser window."""
    if sys.platform == "darwin":
        return _launch_macos_browser(url)
    if sys.platform == "win32" or _use_wsl_browser():
        from cirno_server.cli.windows_browser import launch_browser

        return launch_browser(url)
    return _launch_unix_browser(url)


def _use_wsl_browser() -> bool:
    """Use the Windows desktop in WSL unless the user selected a browser."""
    return (
        sys.platform == "linux" and bool(os.environ.get("WSL_DISTRO_NAME"))
        and not os.environ.get("BROWSER")
    )


def _launch_unix_browser(url: str) -> bool:
    """Launch the selected Unix browser without exposing launcher diagnostics."""
    try:
        webbrowser.get()
    except webbrowser.Error:
        return False
    # get() initializes the stdlib's BROWSER-first ordering. Its public API
    # exposes only the first controller, so read the complete registered order.
    choices: list[str] = getattr(webbrowser, "_tryorder")
    for choice in choices:
        browser = webbrowser.get(choice)
        if isinstance(browser, webbrowser.GenericBrowser):
            # gio, xdg-open, and BROWSER command templates inherit this class.
            # BackgroundBrowser.open only polls once and inherits our stderr.
            command = [browser.name, *(arg.replace("%s", url) for arg in browser.args)]
            sys.audit("webbrowser.open", url)
            if _launch_browser_command(command):
                return True
        elif browser.open(url, new=2, autoraise=True):
            # Native Unix controllers already isolate their subprocess output.
            return True
    return False


def _launch_browser_command(command: list[str]) -> bool:
    """Report an immediate launch failure while allowing a browser to stay open."""
    import subprocess
    import threading

    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True,
        )
    except OSError:
        return False
    try:
        return process.wait(timeout=5) == 0
    except subprocess.TimeoutExpired:
        # A direct browser command can stay alive for the whole browsing session.
        threading.Thread(target=process.wait, daemon=True).start()
        return True




def _launch_macos_browser(url: str) -> bool:
    """Deliver URLs through Launch Services, never a credential-bearing argv."""
    import ctypes

    try:
        foundation = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        services = ctypes.CDLL("/System/Library/Frameworks/CoreServices.framework/CoreServices")
        foundation.CFURLCreateWithBytes.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32, ctypes.c_void_p,
        ]
        foundation.CFURLCreateWithBytes.restype = ctypes.c_void_p
        foundation.CFRelease.argtypes = [ctypes.c_void_p]
        foundation.CFRelease.restype = None
        services.LSOpenCFURLRef.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        services.LSOpenCFURLRef.restype = ctypes.c_int32
        encoded = url.encode("utf-8")
        url_ref = foundation.CFURLCreateWithBytes(None, encoded, len(encoded), 0x08000100, None)
        if not url_ref:
            return False
        try:
            # HTTP URLs reach the preferred browser in a GURL Apple event, not
            # through `open <url>` or a BROWSER command's process arguments.
            return services.LSOpenCFURLRef(url_ref, None) == 0
        finally:
            foundation.CFRelease(url_ref)
    except (OSError, AttributeError, UnicodeError):
        # Callers may display exception text. Keep URLs out of error output and
        # never retry with a subprocess/controller that can expose credentials.
        return False












def _webui_config_dict(config: Config) -> dict[str, Any]:
    """Return the current WebSocket config as a mutable alias-key dictionary."""
    from cirno_server.channels.websocket.runtime import WebSocketConfig

    current: Any = getattr(config.channels, "websocket", None) or {}
    model = WebSocketConfig.model_validate(current)
    return model.model_dump(by_alias=True, exclude_none=True)


def _webui_channel_enabled(config: Config) -> bool:
    from cirno_server.channels.websocket.runtime import WebSocketConfig

    current: Any = getattr(config.channels, "websocket", None) or {}
    return bool(WebSocketConfig.model_validate(current).enabled)




def _prepare_webui_bundle_for_gateway(
    config: Config,
    *,
    mode: BuildMode,
    webui_static_dist: bool = True,
) -> None:
    """Refresh or warn about stale bundled WebUI assets before gateway startup."""
    if not webui_static_dist or not _webui_channel_enabled(config):
        return

    def _print(message: str) -> None:
        console.print(f"[yellow]{escape(message)}[/yellow]")

    def _confirm(message: str) -> bool:
        return typer.confirm(message, default=True)

    try:
        # Interactive WebUI commands keep source and bundle in lockstep.
        # Warn-only gateway startup must not block on a frontend build.
        if mode not in {"skip", "warn"} and inspect_webui_bundle().source_available:
            mode = "auto"
        ensure_webui_bundle(
            mode=mode,
            confirm=_confirm if mode == "prompt" else None,
            output=_print,
        )
    except WebUIBuildError as exc:
        if mode == "warn":
            console.print(f"[yellow]Warning: {escape(str(exc))}[/yellow]")
            return
        console.print(f"[red]Error: {escape(str(exc))}[/red]")
        raise typer.Exit(1) from exc


def _host_for_local_browser(host: str) -> str:
    """Map bind hosts to a browser-openable local host."""
    if host in {"0.0.0.0", ""}:
        return "127.0.0.1"
    if host == "::":
        return "[::1]"
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _gateway_health_url(host: str, port: int) -> str:
    """Return a health URL that can be opened from this device."""
    return f"http://{_host_for_local_browser(host)}:{port}/health"


def _gateway_health_bind_note(host: str) -> str:
    """Describe a non-local bind without presenting it as a usable URL."""
    return "" if is_loopback_host(host) else f" [dim](listening on {host})[/dim]"


def webui_bootstrap_secret(config: Config) -> str:
    """Return the shared local bootstrap credential for WebUI protocol clients."""
    ws_cfg = _webui_config_dict(config)
    return str(ws_cfg.get("tokenIssueSecret") or ws_cfg.get("token") or "").strip()


def _webui_browser_url(config: Config) -> str:
    from urllib.parse import quote

    ws_cfg = _webui_config_dict(config)
    host = _host_for_local_browser(str(ws_cfg.get("host") or "127.0.0.1"))
    port = int(ws_cfg.get("port") or 8765)
    base_url = f"http://{host}:{port}"
    secret = webui_bootstrap_secret(config)
    if not secret:
        return base_url
    return f"{base_url}/#/?bootstrapSecret={quote(secret, safe='')}"


def _webui_display_url(url: str) -> str:
    return url.split("#", 1)[0].rstrip("/")








def _tcp_endpoint_reachable(host: str, port: int, *, timeout_s: float = 0.25) -> bool:
    """Return whether a local TCP endpoint accepts connections."""
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False




def _webui_endpoint_reachable(url: str, *, timeout_s: float = 0.25) -> bool:
    """Return whether the WebUI URL's TCP endpoint is already listening."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return _tcp_endpoint_reachable(host, port, timeout_s=timeout_s)


def _print_foreground_port_conflict(
    *,
    webui_url: str,
    gateway_host: str,
    gateway_port: int,
) -> None:
    console.print("[red]Cannot open this WebUI: the address is already in use.[/red]")
    console.print()
    console.print(Text(f"Page: {_webui_display_url(webui_url)}", style="cyan"), soft_wrap=True)
    console.print(
        Text(f"Service: {_gateway_health_url(gateway_host, gateway_port)}", style="dim"),
        soft_wrap=True,
    )
    console.print()
    console.print("Stop the existing instance from the terminal where you started it.")
    console.print(
        "To run another instance, choose unused ports with "
        "[cyan]--port[/cyan] and [cyan]--health-port[/cyan]."
    )






_LOG_ANCHOR_BYTES = 64
