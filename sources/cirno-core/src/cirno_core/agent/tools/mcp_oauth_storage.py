"""Durable MCP OAuth credentials, write ownership and refresh leases.

This MCP-specific storage is independent of browser/SDK flow orchestration.
Accepted mutations retain ownership through cancellation until their write settles.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import secrets
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, TypedDict, cast

from filelock import AsyncFileLock, BaseAsyncFileLock, FileLock
from loguru import logger
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken
from pydantic import BaseModel

from cirno_core.config.paths import get_config_path
from cirno_core.utils.atomic_file import atomic_write_text as _atomic_write_text
from cirno_core.utils.cancellation import shield_and_drain

_Model = TypeVar("_Model", bound=BaseModel)

_STORE_VERSION = 1

_STORE_LOCK_TIMEOUT_S = 15

_REFRESH_LOCK_TIMEOUT_S = 60

class _StoredServer(TypedDict, total=False):
    server_fingerprint: str
    write_lease: str
    tokens: dict[str, Any]
    expires_at: float
    token_issuer: str
    client_info: dict[str, Any]
    oauth_metadata: dict[str, Any]
    oauth_issuer: str
    redirect_uri: str

class _CredentialStore(TypedDict):
    version: int
    servers: dict[str, _StoredServer]
    generations: dict[str, str]

class MCPAuthorizationRequiredError(RuntimeError):
    """Raised when a background MCP connection needs interactive authorization."""

@dataclass(frozen=True)
class _OAuthSnapshot:
    tokens: OAuthToken | None
    expires_at: float | None
    token_issuer: str | None
    client_info: OAuthClientInformationFull | None
    oauth_metadata: OAuthMetadata | None
    oauth_issuer: str | None

@dataclass(frozen=True)
class _RefreshLease:
    lock: BaseAsyncFileLock
    access_token: str
    refresh_token: str
    token_issuer: str

def _store_path(config_path: Path | None = None) -> Path:
    owner = config_path.expanduser().resolve(strict=False).parent if config_path is not None else get_config_path().parent
    root = owner / "state"
    return root / "auth" / "mcp.json"

def _server_fingerprint(server_url: str) -> str:
    return hashlib.sha256(server_url.strip().encode("utf-8")).hexdigest()

def _normalize_issuer(value: str) -> str:
    return value.rstrip("/")

def _empty_store() -> _CredentialStore:
    return {"version": _STORE_VERSION, "servers": {}, "generations": {}}

def _string_mapping(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    mapping = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        return None
    return cast(dict[str, Any], mapping)


def _stored_server(value: object) -> _StoredServer | None:
    if not isinstance(value, dict):
        return None
    raw = cast(dict[object, object], value)
    entry: _StoredServer = {}
    fingerprint = raw.get("server_fingerprint")
    if isinstance(fingerprint, str):
        entry["server_fingerprint"] = fingerprint
    write_lease = raw.get("write_lease")
    if isinstance(write_lease, str) and write_lease:
        entry["write_lease"] = write_lease
    redirect_uri = raw.get("redirect_uri")
    if isinstance(redirect_uri, str):
        entry["redirect_uri"] = redirect_uri
    tokens = _string_mapping(raw.get("tokens"))
    if tokens is not None:
        entry["tokens"] = tokens
    expires_at = raw.get("expires_at")
    if (
        isinstance(expires_at, (int, float))
        and not isinstance(expires_at, bool)
        and math.isfinite(expires_at)
    ):
        entry["expires_at"] = float(expires_at)
    token_issuer = raw.get("token_issuer")
    if isinstance(token_issuer, str) and token_issuer:
        entry["token_issuer"] = token_issuer
    client_info = _string_mapping(raw.get("client_info"))
    if client_info is not None:
        entry["client_info"] = client_info
    oauth_metadata = _string_mapping(raw.get("oauth_metadata"))
    if oauth_metadata is not None:
        entry["oauth_metadata"] = oauth_metadata
    oauth_issuer = raw.get("oauth_issuer")
    if isinstance(oauth_issuer, str) and oauth_issuer:
        entry["oauth_issuer"] = _normalize_issuer(oauth_issuer)
    return entry

def _read_store_unlocked(path: Path) -> _CredentialStore:
    try:
        raw = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return _empty_store()
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Could not read MCP OAuth credentials: {}", type(exc).__name__)
        return _empty_store()
    if not isinstance(raw, dict):
        return _empty_store()
    payload = cast(dict[object, object], raw)
    raw_servers = payload.get("servers")
    if not isinstance(raw_servers, dict):
        return _empty_store()
    servers: dict[str, _StoredServer] = {}
    for name, value in cast(dict[object, object], raw_servers).items():
        entry = _stored_server(value)
        if isinstance(name, str) and entry is not None:
            servers[name] = entry
    generations: dict[str, str] = {}
    raw_generations = payload.get("generations")
    if isinstance(raw_generations, dict):
        for name, value in cast(dict[object, object], raw_generations).items():
            if isinstance(name, str) and isinstance(value, str) and value:
                generations[name] = value
    return {
        "version": _STORE_VERSION,
        "servers": servers,
        "generations": generations,
    }

def _with_store_lock(path: Path) -> FileLock:
    path.parent.mkdir(parents=True, exist_ok=True)
    return FileLock(str(path.with_suffix(".lock")), timeout=_STORE_LOCK_TIMEOUT_S)

def _write_store_unlocked(path: Path, payload: _CredentialStore) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        os.chmod(path.parent, 0o700)
    _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False))
    with suppress(OSError):
        os.chmod(path, 0o600)

class MCPOAuthStorage:
    """Persistent MCP SDK token storage, isolated by config name and server URL."""

    def __init__(self, server_name: str, server_url: str, *, config_path: Path | None = None) -> None:
        self.server_name = server_name
        self.server_fingerprint = _server_fingerprint(server_url)
        self._path = _store_path(config_path).absolute()
        self._observed_generation = self._read_generation_sync()
        self._write_lease: str | None = None

    def _read_generation_sync(self) -> str | None:
        path = self._path
        if not path.exists():
            return None
        # Writes replace the whole file atomically, so this observes either side
        # of a concurrent deletion without blocking the async connection path.
        return _read_store_unlocked(path)["generations"].get(self.server_name)

    def _generation_is_current(self, payload: _CredentialStore) -> bool:
        return payload["generations"].get(self.server_name) == self._observed_generation

    def _entry_unlocked(self, payload: _CredentialStore) -> _StoredServer | None:
        servers = payload["servers"]
        entry = servers.get(self.server_name)
        if entry is None or entry.get("server_fingerprint") != self.server_fingerprint:
            return None
        return entry

    def _bind_entry_unlocked(
        self,
        payload: _CredentialStore,
        *,
        create: bool,
    ) -> tuple[_StoredServer | None, bool]:
        if not self._generation_is_current(payload):
            return None, False
        entry = self._entry_unlocked(payload)
        if self._write_lease is not None:
            if entry is None or entry.get("write_lease") != self._write_lease:
                return None, False
            return entry, False
        if entry is None:
            if not create:
                return None, False
            self._write_lease = secrets.token_urlsafe(24)
            entry = _StoredServer(
                server_fingerprint=self.server_fingerprint,
                write_lease=self._write_lease,
            )
            payload["servers"][self.server_name] = entry
            return entry, True
        write_lease = entry.get("write_lease")
        changed = not isinstance(write_lease, str) or not write_lease
        if changed:
            write_lease = secrets.token_urlsafe(24)
            entry["write_lease"] = write_lease
        self._write_lease = write_lease
        return entry, changed

    def _read_entry_sync(self) -> _StoredServer | None:
        path = self._path
        with _with_store_lock(path):
            payload = _read_store_unlocked(path)
            entry, changed = self._bind_entry_unlocked(payload, create=False)
            if changed:
                _write_store_unlocked(path, payload)
            return entry

    def _update_entry_sync(
        self,
        update: Callable[[_StoredServer], None],
        *,
        create: bool = True,
        claim: bool = False,
    ) -> bool:
        path = self._path
        with _with_store_lock(path):
            payload = _read_store_unlocked(path)
            if claim:
                # A browser flow owns subsequent SDK writes until another flow
                # claims the entry or the configured server is removed.
                if not self._generation_is_current(payload):
                    logger.info(
                        "Ignored stale MCP OAuth credential claim for '{}'",
                        self.server_name,
                    )
                    return False
                entry = self._entry_unlocked(payload)
                if entry is None:
                    entry = _StoredServer(server_fingerprint=self.server_fingerprint)
                    payload["servers"][self.server_name] = entry
                self._write_lease = secrets.token_urlsafe(24)
                entry["write_lease"] = self._write_lease
            else:
                entry, _ = self._bind_entry_unlocked(payload, create=create)
                if entry is None:
                    if self._write_lease is not None:
                        logger.info(
                            "Ignored stale MCP OAuth credential update for '{}'",
                            self.server_name,
                        )
                    return False
            update(entry)
            payload["version"] = _STORE_VERSION
            _write_store_unlocked(path, payload)
            return True

    async def _update_entry(
        self,
        update: Callable[[_StoredServer], None],
        *,
        create: bool = True,
        claim: bool = False,
    ) -> bool:
        # A cancelled awaiting task cannot stop the worker. Keep its write and
        # lease claim owned until settled, before a replacement flow can start.
        return await shield_and_drain(asyncio.to_thread(
            self._update_entry_sync, update, create=create, claim=claim,
        ))

    def _read_model(
        self, entry: _StoredServer, field: str, model: type[_Model], label: str,
    ) -> _Model | None:
        raw = entry.get(field)
        if not isinstance(raw, dict):
            return None
        try:
            return model.model_validate(raw)
        except (ValueError, TypeError):
            logger.warning("Ignoring invalid MCP OAuth {} for '{}'", label, self.server_name)
            return None

    def _snapshot_from_entry(self, entry: _StoredServer | None) -> _OAuthSnapshot:
        entry = entry or {}
        tokens = self._read_model(entry, "tokens", OAuthToken, "tokens")

        expires_at: float | None = None
        raw_expiry = entry.get("expires_at")
        if isinstance(raw_expiry, (int, float)) and not isinstance(raw_expiry, bool):
            expires_at = float(raw_expiry)

        token_issuer: str | None = None
        raw_token_issuer = entry.get("token_issuer")
        if isinstance(raw_token_issuer, str) and raw_token_issuer:
            token_issuer = raw_token_issuer

        client_info = self._read_model(entry, "client_info", OAuthClientInformationFull, "client info")
        oauth_metadata = self._read_model(entry, "oauth_metadata", OAuthMetadata, "metadata")

        oauth_issuer: str | None = None
        raw_oauth_issuer = entry.get("oauth_issuer")
        if isinstance(raw_oauth_issuer, str) and raw_oauth_issuer:
            oauth_issuer = _normalize_issuer(raw_oauth_issuer)

        return _OAuthSnapshot(
            tokens,
            expires_at,
            token_issuer,
            client_info,
            oauth_metadata,
            oauth_issuer,
        )

    async def get_snapshot(self) -> _OAuthSnapshot:
        entry = await asyncio.to_thread(self._read_entry_sync)
        return self._snapshot_from_entry(entry)

    async def get_tokens(self) -> OAuthToken | None:
        return (await self.get_snapshot()).tokens

    @staticmethod
    def _replace_tokens(entry: _StoredServer, tokens: OAuthToken | None) -> None:
        if tokens is None:
            entry.pop("tokens", None)
            entry.pop("expires_at", None)
            entry.pop("token_issuer", None)
        else:
            entry["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
            if tokens.expires_in is None:
                entry.pop("expires_at", None)
            else:
                entry["expires_at"] = time.time() + float(tokens.expires_in)

    async def set_tokens(self, tokens: OAuthToken) -> None:
        def update(entry: _StoredServer) -> None:
            self._replace_tokens(entry, tokens)
            issuer = entry.get("oauth_issuer")
            if isinstance(issuer, str) and issuer:
                entry["token_issuer"] = _normalize_issuer(issuer)
            else:
                entry.pop("token_issuer", None)

        await self._update_entry(update)

    async def clear_tokens(self) -> None:
        def update(entry: _StoredServer) -> None:
            self._replace_tokens(entry, None)

        await self._update_entry(update, create=False)

    async def clear_tokens_and_client(self) -> None:
        def update(entry: _StoredServer) -> None:
            self._replace_tokens(entry, None)
            entry.pop("client_info", None)

        await self._update_entry(update, create=False)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return (await self.get_snapshot()).client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        raw = client_info.model_dump(mode="json", exclude_none=True)

        def update(entry: _StoredServer) -> None:
            entry["client_info"] = raw

        await self._update_entry(update)

    async def set_oauth_metadata(
        self,
        metadata: OAuthMetadata,
        *,
        issuer: str | None = None,
    ) -> None:
        raw = metadata.model_dump(mode="json", exclude_none=True)
        oauth_issuer = _normalize_issuer(issuer or str(metadata.issuer))

        def update(entry: _StoredServer) -> None:
            entry["oauth_metadata"] = raw
            entry["oauth_issuer"] = oauth_issuer

        await self._update_entry(update)

    async def clear_oauth_metadata(self) -> None:
        def update(entry: _StoredServer) -> None:
            entry.pop("oauth_metadata", None)
            entry.pop("oauth_issuer", None)

        await self._update_entry(update, create=False)

    @staticmethod
    def _token_binding(entry: _StoredServer) -> tuple[str, str, str] | None:
        raw = entry.get("tokens")
        if not isinstance(raw, dict):
            return None
        access_token = raw.get("access_token")
        refresh_token = raw.get("refresh_token")
        token_issuer = entry.get("token_issuer")
        if (
            not isinstance(access_token, str)
            or not access_token
            or not isinstance(refresh_token, str)
            or not refresh_token
            or not isinstance(token_issuer, str)
            or not token_issuer
        ):
            return None
        return access_token, refresh_token, token_issuer

    def refresh_lock(self) -> BaseAsyncFileLock:
        path = self._path
        path.parent.mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha256(
            f"{self.server_name}\0{self.server_fingerprint}".encode("utf-8")
        ).hexdigest()
        return AsyncFileLock(
            path.with_name(f"mcp-refresh-{identity}.lock"),
            timeout=_REFRESH_LOCK_TIMEOUT_S,
        )

    def _finish_refresh_sync(
        self,
        lease: _RefreshLease,
        tokens: OAuthToken | None,
        *,
        clear_client: bool,
    ) -> bool:
        path = self._path
        with _with_store_lock(path):
            payload = _read_store_unlocked(path)
            entry, changed = self._bind_entry_unlocked(payload, create=False)
            if (
                entry is None
                or self._token_binding(entry)
                != (lease.access_token, lease.refresh_token, lease.token_issuer)
            ):
                if changed:
                    _write_store_unlocked(path, payload)
                return False

            self._replace_tokens(entry, tokens)
            if clear_client:
                entry.pop("client_info", None)
            _write_store_unlocked(path, payload)
            return True

    async def finish_refresh(
        self,
        lease: _RefreshLease,
        tokens: OAuthToken | None,
        *,
        clear_client: bool = False,
    ) -> bool:
        return await shield_and_drain(asyncio.to_thread(
            self._finish_refresh_sync,
            lease,
            tokens,
            clear_client=clear_client,
        ))

    async def redirect_uri(self) -> str | None:
        entry = await asyncio.to_thread(self._read_entry_sync)
        value = entry.get("redirect_uri") if entry is not None else None
        return value if isinstance(value, str) and value else None

    async def prepare_redirect_uri(self, redirect_uri: str, *, reset: bool = False) -> None:
        def update(entry: _StoredServer) -> None:
            changed = entry.get("redirect_uri") != redirect_uri
            if reset:
                self._replace_tokens(entry, None)
                entry.pop("client_info", None)
            elif changed:
                # Dynamic registrations bind a client to its redirect URI.
                entry.pop("client_info", None)
            entry["redirect_uri"] = redirect_uri

        claimed = await self._update_entry(update, claim=True)
        if not claimed:
            raise MCPAuthorizationRequiredError("MCP authorization was cancelled")

    def has_credentials(self) -> bool:
        entry = self._read_entry_sync()
        raw_tokens = entry.get("tokens") if entry is not None else None
        if not isinstance(raw_tokens, dict):
            return False
        tokens = cast(dict[str, object], raw_tokens)
        access_token = tokens.get("access_token")
        return isinstance(access_token, str) and bool(access_token)

def mcp_oauth_has_credentials(server_name: str, server_url: str, *, config_path: Path | None = None) -> bool:
    """Return whether this exact configured MCP instance has an access token."""
    # Writers atomically replace the whole file. Presence queries do not own an
    # SDK write lease and must neither wait on its writer lock nor create one.
    entry = _read_store_unlocked(_store_path(config_path))["servers"].get(server_name)
    if entry is None or entry.get("server_fingerprint") != _server_fingerprint(server_url):
        return False
    tokens = entry.get("tokens")
    access = tokens.get("access_token") if isinstance(tokens, dict) else None
    return isinstance(access, str) and bool(access)

def mcp_oauth_stored_server_names(*, config_path: Path | None = None) -> set[str]:
    """List stored identities for owner cleanup without exposing credential values."""
    return set(_read_store_unlocked(_store_path(config_path))["servers"])

def delete_mcp_oauth_credentials(
    server_name: str,
    *,
    config_path: Path | None = None,
    preserve_server_url: str | None = None,
    only_if_present: bool = False,
) -> bool:
    """Delete one server's credentials, optionally preserving its current URL.

    Configuration saves can retry obsolete-token cleanup independently of the
    previous configuration. Check the retained URL under the same file lock as
    deletion so a new authorization is not revoked by that retry. Explicit
    removals retain the default generation rotation even without stored tokens.
    """
    path = _store_path(config_path)
    if only_if_present and not path.exists():
        return False
    with _with_store_lock(path):
        payload = _read_store_unlocked(path)
        servers = payload["servers"]
        entry = servers.get(server_name)
        if (
            preserve_server_url is not None
            and entry is not None
            and entry.get("server_fingerprint") == _server_fingerprint(preserve_server_url)
        ):
            return False
        if only_if_present and entry is None:
            return False
        removed = servers.pop(server_name, None) is not None
        # Rotate even when no entry exists so a flow created before removal cannot
        # claim the name later and resurrect credentials.
        payload["generations"][server_name] = secrets.token_urlsafe(24)
        _write_store_unlocked(path, payload)
        return removed
