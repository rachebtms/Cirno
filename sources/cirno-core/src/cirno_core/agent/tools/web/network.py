"""Web network."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from cirno_core.agent.tools.web.constants import MAX_REDIRECTS
from cirno_core.agent.tools.web.safety import _url_carries_credentials


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL scheme/domain. Does NOT check resolved IPs (use _validate_url_safe for that)."""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except ValueError as e:
        return False, str(e)


def _validate_url_safe(url: str) -> tuple[bool, str]:
    """Validate URL with SSRF protection: scheme, domain, and resolved IP check."""
    from cirno_core.security.network import validate_url_target

    return validate_url_target(url)


def _resolve_url_safe(url: str) -> tuple[bool, str, tuple[str, ...]]:
    """Validate URL and return the resolved IPs to pin during the request."""
    from cirno_core.security.network import resolve_url_target

    return resolve_url_target(url)


def _pinned_dns_transport() -> httpx.AsyncBaseTransport:
    from cirno_core.security.network import PinnedDNSAsyncTransport

    return PinnedDNSAsyncTransport()


def _fetch_client_kwargs(proxy: str | None, timeout: float) -> dict[str, Any]:
    from cirno_core.security.network import httpx_env_proxy_mounts

    kwargs: dict[str, Any] = {"timeout": timeout}
    if proxy:
        kwargs["proxy"] = proxy
    else:
        kwargs["transport"] = _pinned_dns_transport()
        mounts = httpx_env_proxy_mounts()
        if mounts:
            kwargs["mounts"] = mounts
    return kwargs


def _unsafe_url_request_error(exc: BaseException) -> str | None:
    from cirno_core.security.network import UnsafeURLRequestError

    return str(exc) if isinstance(exc, UnsafeURLRequestError) else None


async def _get_with_safe_redirects(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str] | None = None,
) -> tuple[httpx.Response | None, str | None]:
    """GET a URL while validating every redirect target before requesting it."""
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        is_valid, error_msg, _ = _resolve_url_safe(current_url)
        if not is_valid:
            return None, f"Redirect blocked: {error_msg}"

        try:
            response = await client.get(current_url, headers=headers, follow_redirects=False)
        except httpx.RequestError as exc:
            unsafe_error = _unsafe_url_request_error(exc)
            if unsafe_error is not None:
                return None, f"Redirect blocked: {unsafe_error}"
            raise
        is_redirect = 300 <= response.status_code < 400
        if not is_redirect:
            return response, None

        location = response.headers.get("location")
        if not location:
            return response, None

        next_url = urljoin(str(response.url), location)
        is_valid, error_msg = _validate_url_safe(next_url)
        if not is_valid:
            await response.aclose()
            return None, f"Redirect blocked: {error_msg}"

        await response.aclose()
        current_url = next_url

    return None, f"Too many redirects: exceeded limit of {MAX_REDIRECTS}"


async def _stream_with_safe_redirects(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str] | None = None,
) -> tuple[httpx.Response | None, Any | None, str | None, bool]:
    """Open a streamed response while validating every redirect target first."""
    current_url = url
    chain_carries_credentials = _url_carries_credentials(url)
    for _ in range(MAX_REDIRECTS + 1):
        is_valid, error_msg, _ = _resolve_url_safe(current_url)
        if not is_valid:
            return None, None, f"Redirect blocked: {error_msg}", chain_carries_credentials

        stream = client.stream(
            "GET",
            current_url,
            headers=headers,
            follow_redirects=False,
        )
        try:
            response = await stream.__aenter__()
        except httpx.RequestError as exc:
            unsafe_error = _unsafe_url_request_error(exc)
            if unsafe_error is not None:
                return (
                    None,
                    None,
                    f"Redirect blocked: {unsafe_error}",
                    chain_carries_credentials,
                )
            raise
        is_redirect = 300 <= response.status_code < 400
        if not is_redirect:
            return response, stream, None, chain_carries_credentials

        location = response.headers.get("location")
        if not location:
            return response, stream, None, chain_carries_credentials

        next_url = urljoin(str(response.url), location)
        chain_carries_credentials = chain_carries_credentials or _url_carries_credentials(next_url)
        is_valid, error_msg = _validate_url_safe(next_url)
        if not is_valid:
            await stream.__aexit__(None, None, None)
            return None, None, f"Redirect blocked: {error_msg}", chain_carries_credentials

        await stream.__aexit__(None, None, None)
        current_url = next_url

    return (
        None,
        None,
        f"Too many redirects: exceeded limit of {MAX_REDIRECTS}",
        chain_carries_credentials,
    )
