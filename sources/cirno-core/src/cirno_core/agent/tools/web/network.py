"""Web network."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from cirno_core.agent.tools.web.constants import MAX_REDIRECTS
from cirno_core.agent.tools.web.safety import _url_carries_credentials


class ResponseTooLargeError(ValueError):
    """A response exceeded the configured fetch budget before extraction."""


async def _read_response_bounded(response: httpx.Response, max_bytes: int) -> bytes:
    """Count decoded streaming bytes, including when Content-Length is absent."""
    if max_bytes < 1:
        raise ValueError("response byte limit must be positive")
    try:
        announced = int(response.headers.get("content-length", ""))
    except ValueError:
        announced = 0
    if announced > max_bytes:
        raise ResponseTooLargeError(f"Web response exceeds the configured {max_bytes:,}-byte limit")
    body = bytearray()
    async for chunk in response.aiter_bytes(chunk_size=min(64 * 1024, max_bytes + 1)):
        if len(body) + len(chunk) > max_bytes:
            raise ResponseTooLargeError(f"Web response exceeds the configured {max_bytes:,}-byte limit")
        body.extend(chunk)
    return bytes(body)


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
    *, max_response_bytes: int | None = None,
) -> tuple[httpx.Response | None, str | None]:
    """GET a URL while validating every redirect target before requesting it."""
    if max_response_bytes is not None:
        response, stream, error, _ = await _stream_with_safe_redirects(client, url, headers)
        if response is None or stream is None:
            return None, error
        try:
            body = await _read_response_bounded(response, max_response_bytes)
            # aiter_bytes already decoded Content-Encoding. Retain type/charset,
            # but never ask the reconstructed response to decompress it again.
            decoded_headers = response.headers.copy()
            decoded_headers.pop("content-encoding", None)
            decoded_headers.pop("content-length", None)
            return httpx.Response(response.status_code, headers=decoded_headers, content=body,
                                  request=response.request, extensions=response.extensions), None
        finally:
            await stream.__aexit__(None, None, None)
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        is_valid, error_msg, _ = await asyncio.to_thread(_resolve_url_safe, current_url)
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

        try:
            next_url = urljoin(str(response.url), location)
            is_valid, error_msg = await asyncio.to_thread(_validate_url_safe, next_url)
        except ValueError:
            return None, "Redirect blocked: invalid redirect URL"
        finally:
            await response.aclose()
        if not is_valid:
            return None, f"Redirect blocked: {error_msg}"

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
        is_valid, error_msg, _ = await asyncio.to_thread(_resolve_url_safe, current_url)
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

        try:
            next_url = urljoin(str(response.url), location)
            chain_carries_credentials = chain_carries_credentials or _url_carries_credentials(next_url)
            is_valid, error_msg = await asyncio.to_thread(_validate_url_safe, next_url)
        except ValueError:
            return None, None, "Redirect blocked: invalid redirect URL", chain_carries_credentials
        finally:
            await stream.__aexit__(None, None, None)
        if not is_valid:
            return None, None, f"Redirect blocked: {error_msg}", chain_carries_credentials

        current_url = next_url

    return (
        None,
        None,
        f"Too many redirects: exceeded limit of {MAX_REDIRECTS}",
        chain_carries_credentials,
    )
