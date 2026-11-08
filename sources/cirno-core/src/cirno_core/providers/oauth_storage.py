"""Instance-owned OAuth credentials using the SDK's public storage protocol."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from cirno_core.config.paths import get_data_dir
from cirno_core.utils.atomic_file import atomic_write_text
from filelock import FileLock
from oauth_cli_kit import get_token
from oauth_cli_kit.models import OAuthToken
from oauth_cli_kit.providers import OPENAI_CODEX_PROVIDER


class InstanceOAuthStorage:
    def __init__(self, path: Path):
        self.path = path
        self._lock = FileLock(path.with_suffix(".operation.lock"))

    def get_token_path(self) -> Path:
        return self.path

    def load(self) -> OAuthToken | None:
        try:
            content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("expected an OAuth credential object")
            if not isinstance(data.get("access"), str) or not data["access"]:
                raise ValueError("access token must be nonempty text")
            if not isinstance(data.get("refresh"), str):
                raise ValueError("refresh token must be text")
            if not isinstance(data.get("expires"), int) or isinstance(data["expires"], bool):
                raise ValueError("expiry must be an integer")
            if data.get("account_id") is not None and not isinstance(data["account_id"], str):
                raise ValueError("account ID must be text or null")
            return OAuthToken(data["access"], data["refresh"], data["expires"], data.get("account_id"))
        except ValueError as error:
            raise ValueError(f"Invalid OAuth credentials at {self.path}: {error}") from error

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._lock:
            yield

    def save(self, token: OAuthToken) -> None:
        with self.transaction():
            atomic_write_text(self.path, json.dumps(asdict(token), ensure_ascii=True, indent=2))

    def delete(self) -> None:
        with self.transaction():
            self.path.unlink(missing_ok=True)


def token_storage(provider_id: str, filename: str) -> InstanceOAuthStorage:
    return InstanceOAuthStorage(get_data_dir() / "providers" / provider_id / filename)


def available_codex_token(*, storage: InstanceOAuthStorage, proxy: str | None = None) -> OAuthToken:
    # Hold ownership across the SDK's initial read and refresh, so a concurrent
    # sign-out cannot be followed by a late refresh writing the login back.
    with storage.transaction():
        return get_token(provider=OPENAI_CODEX_PROVIDER, storage=storage, proxy=proxy)
