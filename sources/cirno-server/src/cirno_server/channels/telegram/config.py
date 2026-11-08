"""Telegram connection and delivery configuration."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from cirno_core.config.base import Base
from pydantic import Field, field_validator, model_validator


class TelegramConfig(Base):
    """Telegram channel configuration."""

    enabled: bool = False
    token: str = ""
    mode: Literal["polling", "webhook"] = "polling"
    use_proxy: bool = False
    reply_to_message: bool = False
    react_emoji: str = "👀"
    connection_pool_size: int = 32
    pool_timeout: float = 5.0
    streaming: bool = True
    # Enable inline keyboard buttons in Telegram messages.
    inline_keyboards: bool = False
    # Opt in to Bot API 10.1 sendRichMessage for richer markdown rendering.
    rich_messages: bool = False
    stream_edit_interval: float = Field(default=0.6, ge=0.1)
    webhook_url: str = ""
    webhook_listen_host: str = "127.0.0.1"
    webhook_listen_port: int = Field(default=8081, ge=1, le=65535)
    webhook_path: str = "/telegram"
    webhook_secret_token: str = ""
    webhook_max_connections: int = Field(default=4, ge=1, le=100)

    @field_validator("webhook_path")
    @classmethod
    def webhook_path_must_start_with_slash(cls, value: str) -> str:
        value = value.strip() or "/telegram"
        if not value.startswith("/"):
            raise ValueError('webhook_path must start with "/"')
        return value

    @model_validator(mode="after")
    def validate_webhook_config(self) -> "TelegramConfig":
        if self.mode != "webhook":
            return self

        url = self.webhook_url.strip()
        if not url:
            raise ValueError("webhook_url is required when Telegram mode is webhook")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("webhook_url must be a public HTTPS URL")
        secret = self.webhook_secret_token.strip()
        if not secret:
            raise ValueError("webhook_secret_token is required when Telegram mode is webhook")
        if len(secret) > 256 or re.match(r"^[A-Za-z0-9_-]+$", secret) is None:
            raise ValueError(
                "webhook_secret_token must be 1-256 characters using only A-Z, a-z, 0-9, _ and -"
            )
        return self
