"""OAuth support for remote MCP servers.

SDK/browser flows consume the MCP-specific durable storage contract. Provider
OAuth has a different lifecycle; its workflow remains separate.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx
from loguru import logger
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientMetadata, OAuthToken
from pydantic import AnyHttpUrl, AnyUrl

from cirno_core.agent.tools.mcp_oauth_storage import (
    MCPAuthorizationRequiredError as MCPAuthorizationRequiredError,
    MCPOAuthStorage as MCPOAuthStorage,
    _OAuthSnapshot,
    _RefreshLease,
    _normalize_issuer,
    delete_mcp_oauth_credentials as delete_mcp_oauth_credentials,
    mcp_oauth_has_credentials as mcp_oauth_has_credentials,
    mcp_oauth_stored_server_names as mcp_oauth_stored_server_names,
)

MCP_OAUTH_CALLBACK_PATH = "/v0/mcp/oauth/callback"
_DEFAULT_REDIRECT_URI = f"http://127.0.0.1{MCP_OAUTH_CALLBACK_PATH}"
_CLIENT_URI = AnyHttpUrl("https://github.com/rachebtms/Cirno")
_LOGO_URI = AnyHttpUrl(
    "https://raw.githubusercontent.com/rachebtms/Cirno/main/"
    "sources/cirno-web/public/brand/cirno_snowflake_apple_touch.png"
)


@dataclass(frozen=True)
class MCPOAuthHandlers:
    """Browser callbacks supplied only for a user-initiated OAuth attempt."""

    redirect_uri: str
    redirect_handler: Callable[[str], Awaitable[None]]
    callback_handler: Callable[[], Awaitable[tuple[str, str | None]]]
    reset_credentials: bool = False


class MCPTokenRefreshError(RuntimeError):
    """Raised when a refresh failed without proving that authorization is invalid."""


class _RetryOAuthWithDiscoveredMetadata(BaseException):
    """Restart the SDK flow after discovery without logging a false OAuth failure."""


class _OAuthAuthorizationInterrupted(BaseException):
    """Carry expected authorization state past the SDK's generic error logger."""

    def __init__(self, error: MCPAuthorizationRequiredError) -> None:
        self.error = error
        super().__init__(str(error))


class _RetryOAuthWithStoredCredentials(BaseException):
    """Restart the SDK flow with credentials refreshed by another provider."""


def _oauth_error_code(response: httpx.Response) -> str | None:
    try:
        payload = cast(object, response.json())
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    error = cast(dict[object, object], payload).get("error")
    return error if isinstance(error, str) else None


class _RefreshingOAuthClientProvider(OAuthClientProvider):
    """MCP SDK OAuth provider with restart-safe, one-shot token refresh.

    This is a compatibility layer for modelcontextprotocol/python-sdk#3328.
    Its private SDK method contract is pinned by tests and should be removed once
    the upstream fix is available in cirno's supported MCP version.
    """

    def __init__(
        self,
        server_url: str,
        client_metadata: OAuthClientMetadata,
        storage: MCPOAuthStorage,
        redirect_handler: Callable[[str], Awaitable[None]] | None = None,
        callback_handler: Callable[[], Awaitable[tuple[str, str | None]]] | None = None,
        timeout: float = 300.0,
    ) -> None:
        self._cirno_storage = storage
        self._refresh_attempted = ContextVar("mcp_oauth_refresh_attempted", default=False)
        self._refresh_after_discovery = ContextVar(
            "mcp_oauth_refresh_after_discovery",
            default=False,
        )
        self._refresh_claim = ContextVar[_RefreshLease | None](
            "mcp_oauth_refresh_claim",
            default=None,
        )
        self._token_issuer: str | None = None
        super().__init__(
            server_url,
            client_metadata,
            storage,
            redirect_handler=redirect_handler,
            callback_handler=callback_handler,
            timeout=timeout,
        )

    async def _initialize(self) -> None:
        """Restore enough OAuth state to refresh without an interactive flow."""
        self._apply_snapshot(await self._cirno_storage.get_snapshot())
        self._initialized = True

    def _apply_snapshot(self, snapshot: _OAuthSnapshot) -> None:
        self.context.current_tokens = snapshot.tokens
        self.context.token_expiry_time = snapshot.expires_at
        if snapshot.oauth_metadata is None or snapshot.oauth_issuer is None:
            # Defer the SDK's pre-request refresh until a 401 discovers metadata.
            # Keep the persisted expiry and issuer binding for retries and restarts.
            self.context.token_expiry_time = None
        self._token_issuer = snapshot.token_issuer
        self.context.client_info = snapshot.client_info
        self.context.oauth_metadata = snapshot.oauth_metadata
        self.context.auth_server_url = snapshot.oauth_issuer

    async def _reload_after_lost_claim(self, lease: _RefreshLease) -> bool:
        snapshot = await self._cirno_storage.get_snapshot()
        self._apply_snapshot(snapshot)
        tokens = snapshot.tokens
        if tokens is None:
            return False
        if (tokens.access_token, tokens.refresh_token) != (
            lease.access_token,
            lease.refresh_token,
        ):
            return True
        raise MCPTokenRefreshError("MCP OAuth credentials changed while refreshing; retry later")

    async def _release_refresh_claim(self) -> None:
        lease = self._refresh_claim.get()
        if lease is None:
            return
        self._refresh_claim.set(None)
        await lease.lock.release()

    async def _handle_refresh_response(self, response: httpx.Response) -> bool:
        """Persist a rotated token pair while retaining credentials on transient errors."""
        lease = self._refresh_claim.get()
        if lease is None:
            raise MCPTokenRefreshError("MCP OAuth refresh response has no storage lease")

        if response.status_code != 200:
            error = _oauth_error_code(response)
            if error in {"invalid_grant", "invalid_client", "unauthorized_client"}:
                clear_client = error != "invalid_grant"
                cleared = await self._cirno_storage.finish_refresh(
                    lease,
                    None,
                    clear_client=clear_client,
                )
                await self._release_refresh_claim()
                if not cleared:
                    return await self._reload_after_lost_claim(lease)
                self.context.clear_tokens()
                self._token_issuer = None
                if clear_client:
                    self.context.client_info = None
                return False
            if response.status_code == 404:
                await self._release_refresh_claim()
                await self._cirno_storage.clear_oauth_metadata()
                self.context.oauth_metadata = None
                self._refresh_attempted.set(False)
                return False
            await self._release_refresh_claim()
            raise MCPTokenRefreshError(
                f"MCP OAuth token refresh failed ({response.status_code}); will retry later"
            )

        try:
            token_response = OAuthToken.model_validate_json(await response.aread())
        except (ValueError, TypeError) as exc:
            await self._release_refresh_claim()
            raise MCPTokenRefreshError("MCP OAuth token refresh returned an invalid response") from exc

        previous = self.context.current_tokens
        updates: dict[str, str] = {}
        if previous is not None:
            if token_response.refresh_token is None and previous.refresh_token is not None:
                updates["refresh_token"] = previous.refresh_token
            if token_response.scope is None and previous.scope is not None:
                updates["scope"] = previous.scope
        if updates:
            token_response = token_response.model_copy(update=updates)

        committed = await self._cirno_storage.finish_refresh(lease, token_response)
        await self._release_refresh_claim()
        if not committed:
            return await self._reload_after_lost_claim(lease)
        self.context.current_tokens = token_response
        self.context.update_token_expiry(token_response)
        return True

    async def _refresh_token(self) -> httpx.Request:
        tokens = self.context.current_tokens
        if tokens is None or tokens.refresh_token is None:
            return await super()._refresh_token()
        lock = self._cirno_storage.refresh_lock()
        await lock.acquire()
        try:
            snapshot = await self._cirno_storage.get_snapshot()
        except BaseException:
            await lock.release()
            raise
        stored_tokens = snapshot.tokens
        if stored_tokens is None or (
            stored_tokens.access_token,
            stored_tokens.refresh_token,
            snapshot.token_issuer,
        ) != (tokens.access_token, tokens.refresh_token, self._token_issuer):
            await lock.release()
            self._apply_snapshot(snapshot)
            raise _RetryOAuthWithStoredCredentials
        metadata = self.context.oauth_metadata
        token_issuer = self._token_issuer
        oauth_issuer = self.context.auth_server_url
        if metadata is None or oauth_issuer is None or token_issuer != _normalize_issuer(oauth_issuer):
            try:
                await self._cirno_storage.clear_tokens()
            finally:
                await lock.release()
            self.context.clear_tokens()
            self._token_issuer = None
            raise _RetryOAuthWithStoredCredentials
        assert token_issuer is not None
        lease = _RefreshLease(
            lock=lock,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_issuer=token_issuer,
        )
        self._refresh_claim.set(lease)
        self._refresh_attempted.set(True)
        try:
            return await super()._refresh_token()
        except BaseException:
            await self._release_refresh_claim()
            raise

    async def _perform_authorization(self) -> httpx.Request:
        metadata = self.context.oauth_metadata
        oauth_issuer: str | None = None
        if metadata is not None:
            oauth_issuer = _normalize_issuer(self.context.auth_server_url or str(metadata.issuer))
            await self._cirno_storage.set_oauth_metadata(metadata, issuer=oauth_issuer)
        if self._refresh_after_discovery.get():
            if metadata is not None and oauth_issuer == self._token_issuer:
                raise _RetryOAuthWithDiscoveredMetadata
            await self._cirno_storage.clear_tokens_and_client()
            self.context.clear_tokens()
            self.context.client_info = None
            self._token_issuer = None
            raise _RetryOAuthWithStoredCredentials
        try:
            return await super()._perform_authorization()
        except MCPAuthorizationRequiredError as exc:
            raise _OAuthAuthorizationInterrupted(exc) from exc

    async def async_auth_flow(
        self,
        request: httpx.Request,
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        """Let a 401 discover the token endpoint, then restart once to refresh."""
        try:
            for attempt in range(3):
                self._refresh_attempted.set(False)
                self._refresh_after_discovery.set(False)
                try:
                    async with aclosing(super().async_auth_flow(request)) as flow:
                        try:
                            outgoing = await anext(flow)
                        except StopAsyncIteration:
                            return
                        while True:
                            response = yield outgoing
                            if (
                                attempt == 0
                                and outgoing is request
                                and response.status_code == 401
                                and not self._refresh_attempted.get()
                                and self.context.can_refresh_token()
                            ):
                                self._refresh_after_discovery.set(True)
                            try:
                                outgoing = await flow.asend(response)
                            except StopAsyncIteration:
                                return
                except _OAuthAuthorizationInterrupted as exc:
                    logger.info(
                        "MCP server '{}': OAuth request stopped at browser authorization",
                        self._cirno_storage.server_name,
                    )
                    raise exc.error from None
                except _RetryOAuthWithDiscoveredMetadata:
                    # The SDK has now validated discovery metadata. Mark the token
                    # expired so its normal pre-request branch refreshes against the
                    # discovered endpoint instead of guessing {server_origin}/token.
                    self.context.token_expiry_time = time.time() - 1
                    continue
                except _RetryOAuthWithStoredCredentials:
                    continue
                finally:
                    self._refresh_after_discovery.set(False)
            raise AssertionError("MCP OAuth refresh retry did not complete")
        finally:
            await self._release_refresh_claim()


async def _missing_callback() -> tuple[str, str | None]:
    raise MCPAuthorizationRequiredError("MCP server requires browser authorization")


async def create_mcp_oauth_auth(
    server_name: str,
    server_url: str,
    handlers: MCPOAuthHandlers | None = None,
    *, config_path: Path | None = None,
) -> OAuthClientProvider:
    """Build the official MCP SDK OAuth provider for one configured server."""
    storage = MCPOAuthStorage(server_name, server_url, config_path=config_path)
    if handlers is not None:
        await storage.prepare_redirect_uri(
            handlers.redirect_uri,
            reset=handlers.reset_credentials,
        )
        redirect_uri = handlers.redirect_uri
        redirect_handler = handlers.redirect_handler
        callback_handler = handlers.callback_handler
    else:
        if not await asyncio.to_thread(storage.has_credentials):
            # Do not perform discovery or dynamic registration from a background
            # startup. Interactive OAuth begins only after an explicit user action.
            raise MCPAuthorizationRequiredError("MCP server requires browser authorization")
        redirect_uri = await storage.redirect_uri() or _DEFAULT_REDIRECT_URI

        async def authorization_required(_authorization_url: str) -> None:
            await storage.clear_tokens()
            raise MCPAuthorizationRequiredError("MCP server requires browser authorization")

        redirect_handler = authorization_required
        callback_handler = _missing_callback

    metadata = OAuthClientMetadata(
        redirect_uris=[AnyUrl(redirect_uri)],
        token_endpoint_auth_method="none",
        client_name="cirno",
        client_uri=_CLIENT_URI,
        logo_uri=_LOGO_URI,
        software_id="https://github.com/rachebtms/Cirno",
    )
    return _RefreshingOAuthClientProvider(
        server_url,
        metadata,
        storage,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
        timeout=300,
    )
