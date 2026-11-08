"""WebSocket transport settings and trusted proxy authentication policy."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit, urlunsplit

from cirno_core.config.base import Base
from pydantic import Field, PrivateAttr, field_validator, model_validator

from cirno_server.api import WEBSOCKET_PATH, require_api_path
from cirno_server.webui.http_utils import normalize_config_path as _normalize_config_path

_ROUTING_ASSERTION_HEADERS = frozenset(
    {
        "host",
        "forwarded",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-real-ip",
        "cf-connecting-ip",
    }
)


def _is_routing_assertion_header(value: str) -> bool:
    normalized = value.casefold()
    return normalized in _ROUTING_ASSERTION_HEADERS or normalized.startswith("x-forwarded-")


class TrustedProxyAuthConfig(Base):
    """Authentication assertions accepted from explicitly trusted proxy peers."""

    trusted_peer_cidrs: list[str] = Field(min_length=1)
    assertion_header: str = Field(min_length=1)
    _trusted_peer_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = PrivateAttr(
        default=()
    )

    @field_validator("trusted_peer_cidrs")
    @classmethod
    def validate_trusted_peer_cidrs(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            value = value.strip()
            try:
                network = ipaddress.ip_network(value, strict=False)
            except ValueError as exc:
                raise ValueError(f"invalid trusted proxy CIDR: {value!r}") from exc
            if network.prefixlen == 0:
                raise ValueError("universal trusted proxy CIDRs are not allowed")
            if isinstance(network, ipaddress.IPv6Network):
                mapped_start = ipaddress.IPv6Address("::ffff:0:0")
                mapped_end = ipaddress.IPv6Address("::ffff:ffff:ffff")
                if mapped_start in network and mapped_end in network:
                    raise ValueError("trusted proxy CIDRs must not cover all IPv4-mapped addresses")
            normalized.append(network.with_prefixlen)
        return normalized

    @field_validator("assertion_header")
    @classmethod
    def validate_assertion_header(cls, value: str) -> str:
        value = value.strip()
        if not value or any(char.isspace() or ord(char) < 0x21 for char in value):
            raise ValueError("assertion_header must be a valid HTTP header name")
        if _is_routing_assertion_header(value):
            raise ValueError(
                "assertion_header must identify a proxy-generated authentication assertion, "
                "not a routing or client metadata header"
            )
        return value

    @model_validator(mode="after")
    def compile_trusted_peer_networks(self) -> Self:
        self._trusted_peer_networks = tuple(
            ipaddress.ip_network(value, strict=False) for value in self.trusted_peer_cidrs
        )
        return self


class WebSocketConfig(Base):
    """WebSocket transport and browser authentication configuration.

    Connections multiplex conversation streams; conversation IDs are independent
    of browser connections. Uploaded attachments use the authenticated HTTP API.
    """

    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    unix_socket_path: str = ""
    path: str = WEBSOCKET_PATH
    public_ws_url: str = ""
    token: str = ""
    token_issue_path: str = ""
    token_issue_secret: str = ""
    browser_setup: bool = False
    trusted_proxy_auth: TrustedProxyAuthConfig | None = None
    token_ttl_s: int = Field(default=300, ge=30, le=86_400)
    websocket_requires_token: bool = True
    allow_from: list[str] = Field(default_factory=lambda: ["*"])
    streaming: bool = True
    # JSON frame budget; HTTP uploads have separate attachment limits.
    max_message_bytes: int = Field(default=37_748_736, ge=1024, le=41_943_040)
    ping_interval_s: float = Field(default=20.0, ge=5.0, le=300.0)
    ping_timeout_s: float = Field(default=20.0, ge=5.0, le=300.0)
    ssl_certfile: str = ""
    ssl_keyfile: str = ""

    @field_validator("unix_socket_path")
    @classmethod
    def unix_socket_path_format(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if "\x00" in value:
            raise ValueError("unix_socket_path must not contain NUL bytes")
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("unix_socket_path must be an absolute path")
        return str(path)

    @field_validator("path")
    @classmethod
    def path_must_start_with_slash(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError('path must start with "/"')
        return require_api_path(_normalize_config_path(value))

    @field_validator("token_issue_path")
    @classmethod
    def token_issue_path_format(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if not value.startswith("/"):
            raise ValueError('token_issue_path must start with "/"')
        return require_api_path(_normalize_config_path(value))

    @field_validator("public_ws_url")
    @classmethod
    def public_ws_url_format(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"ws", "wss"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("public_ws_url must be an absolute ws:// or wss:// URL without credentials")
        return urlunsplit(
            (parsed.scheme, parsed.netloc, _normalize_config_path(parsed.path or "/"), "", "")
        )

    @model_validator(mode="after")
    def public_ws_url_matches_path(self) -> Self:
        if self.public_ws_url and urlsplit(self.public_ws_url).path != _normalize_config_path(self.path):
            raise ValueError("public_ws_url path must match path")
        return self

    @model_validator(mode="after")
    def token_issue_path_differs_from_ws_path(self) -> Self:
        if not self.token_issue_path:
            return self
        if _normalize_config_path(self.token_issue_path) == _normalize_config_path(self.path):
            raise ValueError("token_issue_path must differ from path (the WebSocket upgrade path)")
        return self

    @model_validator(mode="after")
    def wildcard_host_requires_auth(self) -> Self:
        if self.host not in ("0.0.0.0", "::"):
            return self
        if self.browser_setup or self.token.strip() or self.token_issue_secret.strip() or self.trusted_proxy_auth is not None:
            return self
        raise ValueError(
            "host is 0.0.0.0 (all interfaces) but neither browser_setup, token, token_issue_secret, "
            "nor trusted_proxy_auth is set — set one to prevent unauthenticated access"
        )
