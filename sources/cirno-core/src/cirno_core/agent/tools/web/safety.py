"""Web safety."""

from __future__ import annotations

import os
import re
from urllib.parse import parse_qsl, unquote, urlparse

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

_SEARCH_API_KEY_ENV_VARS = (
    "BRAVE_API_KEY", "TAVILY_API_KEY", "JINA_API_KEY", "KAGI_API_KEY", "EXA_API_KEY",
    "OLOSTEP_API_KEY", "BOCHA_API_KEY", "VOLCENGINE_SEARCH_API_KEY", "WEB_SEARCH_API_KEY",
    "KEENABLE_API_KEY", "ANYSEARCH_API_KEY", "SERPER_API_KEY",
)


def _redact_search_error(text: str, *, api_key: str, proxy: str | None, base_url: str) -> str:
    """Remove known search credentials from upstream diagnostic text."""
    secrets = {api_key, *(os.environ.get(name, "") for name in _SEARCH_API_KEY_ENV_VARS)}
    for value in (proxy, base_url, os.environ.get("SEARXNG_BASE_URL", "")):
        if not value:
            continue
        try:
            parsed = urlparse(value)
        except ValueError:
            secrets.add(value)
            continue
        if parsed.username is not None or parsed.password is not None:
            secrets.add(value)
            for credential in (parsed.username, parsed.password):
                if credential:
                    secrets.update((credential, unquote(credential)))
        for name, credential in parse_qsl(parsed.query.replace(";", "&"), keep_blank_values=True):
            lowered = name.strip().lower()
            if lowered in _CREDENTIAL_QUERY_PARAMS or lowered.startswith(_CREDENTIAL_QUERY_PREFIXES):
                secrets.update((value, credential))
    patterns = [re.escape(value) for value in sorted(secrets, key=len, reverse=True) if value]
    return re.sub("|".join(patterns), "[redacted]", text) if patterns else text


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
