"""Classify explicit provider endpoints and required attribution headers."""

from ipaddress import ip_address
from urllib.parse import urlparse

from cirno_core.providers.catalog.contracts import ProviderSpec


def _endpoint_host(api_base: str | None) -> str:
    try:
        return (urlparse(api_base or "").hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def uses_openrouter_attribution(spec: "ProviderSpec | None", api_base: str | None) -> bool:
    """Apply Cirno attribution headers to OpenRouter requests by default."""
    if spec and spec.name == "openrouter":
        return True
    host = _endpoint_host(api_base)
    return host == "openrouter.ai" or host.endswith(".openrouter.ai")


def uses_opencode_affinity(spec: ProviderSpec | None, api_base: str | None) -> bool:
    if spec and spec.name in {"opencode", "opencode_go"}:
        return True
    host = _endpoint_host(api_base)
    return host == "opencode.ai" or host.endswith(".opencode.ai")


def is_local_endpoint(
    spec: "ProviderSpec | None",
    api_base: str | None,
) -> bool:
    """Return True when the endpoint is a local or LAN model server.

    Matches either the provider spec's ``is_local`` flag or common private-
    network patterns in the base URL (localhost, 127.x, 192.168.x, 10.x,
    172.16-31.x, Docker ``host.docker.internal``).
    """
    if spec and spec.is_local:
        return True
    if not api_base:
        return False
    raw = api_base.strip().lower()
    host = _endpoint_host(raw if "://" in raw else f"//{raw}")
    if host in {"localhost", "host.docker.internal"}:
        return True
    if not host:
        return False
    try:
        addr = ip_address(host)
    except ValueError:
        return False
    return addr.is_loopback or addr.is_private
