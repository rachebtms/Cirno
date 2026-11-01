"""Single-owner credentials and revocable browser sessions, scoped to an instance."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SESSION_SECONDS = 30 * 24 * 60 * 60


class AccountError(ValueError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _password_hash(password: str, salt: bytes) -> bytes:
    # A bounded 16 MiB working set also fits the small-server deployment target.
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)


class AccountStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Credentials should not inherit a permissive process umask.
        self.path.touch(mode=0o600, exist_ok=True)
        self.path.chmod(0o600)
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS owner (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    username TEXT NOT NULL,
                    salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    onboarded INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    expires_at REAL NOT NULL
                );
            """)
            with connection:
                yield connection
        finally:
            connection.close()

    def owner(self) -> tuple[str, bool] | None:
        if not self.path.exists():
            return None
        with self._connect() as connection:
            row = connection.execute("SELECT username, onboarded FROM owner WHERE id = 1").fetchone()
        return (str(row[0]), bool(row[1])) if row else None

    def register(self, username: object, password: object) -> str:
        if not isinstance(username, str) or not 1 <= len(username.strip()) <= 64:
            raise AccountError("invalid_username")
        if (
            not isinstance(password, str)
            or len(password) < 10
            or not any(unicodedata.category(character) == "Lu" for character in password)
            or not any(unicodedata.category(character)[0] in {"P", "S"} for character in password)
        ):
            raise AccountError("invalid_password")
        salt = secrets.token_bytes(16)
        hashed = _password_hash(password, salt)
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO owner (id, username, salt, password_hash) VALUES (1, ?, ?, ?)",
                    (username.strip(), salt, hashed),
                )
            except sqlite3.IntegrityError as exc:
                raise AccountError("registration_closed", 409) from exc
            return self._create_session(connection)

    def login(self, username: object, password: object) -> str:
        if not isinstance(username, str) or not isinstance(password, str):
            raise AccountError("invalid_credentials", 401)
        with self._connect() as connection:
            row = connection.execute("SELECT username, salt, password_hash FROM owner WHERE id = 1").fetchone()
            if row is None:
                raise AccountError("registration_required", 409)
            hashed = _password_hash(password, row[1])
            if not hmac.compare_digest(username.strip().encode(), row[0].encode()) or not hmac.compare_digest(hashed, row[2]):
                raise AccountError("invalid_credentials", 401)
            return self._create_session(connection)

    @staticmethod
    def _create_session(connection: sqlite3.Connection) -> str:
        token = secrets.token_urlsafe(32)
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (time.time(),))
        connection.execute(
            "INSERT INTO sessions VALUES (?, ?)",
            (hashlib.sha256(token.encode()).hexdigest(), time.time() + SESSION_SECONDS),
        )
        return token

    def authenticated(self, token: str) -> bool:
        if not token or len(token) > 128 or not self.path.exists():
            return False
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM sessions WHERE token_hash = ? AND expires_at > ?",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
        return row is not None

    def logout(self, token: str) -> None:
        if self.path.exists():
            with self._connect() as connection:
                connection.execute("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))

    def complete_onboarding(self) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE owner SET onboarded = 1 WHERE id = 1")
