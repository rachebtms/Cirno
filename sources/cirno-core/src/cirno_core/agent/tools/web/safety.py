"""Web safety."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlparse

from cirno_core.agent.tools.context import tool_log_content_allowed

_CREDENTIAL_QUERY_PARAMS = frozenset(
    {
        "access_token",
        "api-key",
        "api-token",
        "apikey",
        "api_key",
        "api_token",
        "auth",
        "authorization",
        "client_assertion",
        "client_secret",
        "code",
        "credential",
        "credentials",
        "id_token",
        "jwt",
        "key",
        "password",
        "passwd",
        "private_key",
        "pwd",
        "refresh_token",
        "samlresponse",
        "secret",
        "session_id",
        "session_token",
        "sessionid",
        "sig",
        "signature",
        "sso_token",
        "ticket",
        "token",
    }
)


_CREDENTIAL_QUERY_PREFIXES = ("x-amz-", "x-goog-")


def _url_carries_credentials(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return True
    if parsed.username is not None or parsed.password is not None:
        return True
    # Some frameworks still accept semicolons as query separators. Treating
    # them as separators here may over-match a value, but the safe consequence
    # is only using the local extractor instead of disclosing a credential.
    query = parsed.query.replace(";", "&")
    for name, _value in parse_qsl(query, keep_blank_values=True):
        lowered = name.strip().lower()
        if lowered in _CREDENTIAL_QUERY_PARAMS or lowered.startswith(_CREDENTIAL_QUERY_PREFIXES):
            return True
    return False


def _redact_url_for_log(url: str) -> str:
    """Return only a URL's origin, excluding userinfo, path, query, and fragment."""
    if not tool_log_content_allowed():
        return "[content hidden]"
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not parsed.scheme or hostname is None:
            return "<redacted URL>"
        if ":" in hostname:
            hostname = f"[{hostname}]"
        try:
            port = parsed.port
        except ValueError:
            port = None
        authority = f"{hostname}:{port}" if port is not None else hostname
        return f"{parsed.scheme}://{authority}"
    except ValueError:
        return "<redacted URL>"
