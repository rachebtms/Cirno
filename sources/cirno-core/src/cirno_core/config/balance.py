"""Optional provider account balance endpoint, independent of model routing."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from cirno_core.config.base import Base


class ProviderBalanceConfig(Base):
    endpoint: str = Field(min_length=1, max_length=4096)
    format: Literal["deepseek", "json"] = "deepseek"
    amount_path: str = Field(default="/balance", max_length=512)
    currency: str = Field(default="USD", min_length=1, max_length=24)
    api_key: str | None = Field(default=None, repr=False)

    @field_validator("endpoint")
    @classmethod
    def http_endpoint(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("${") and value.endswith("}"):
            return value
        try:
            parsed = urlsplit(value)
            valid = (
                parsed.scheme in {"http", "https"} and parsed.hostname
                and parsed.port != 0
                and parsed.username is None and parsed.password is None
                and not parsed.fragment
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("Enter an HTTP(S) balance endpoint with a valid port, without embedded credentials or a fragment")
        return value

    @field_validator("amount_path")
    @classmethod
    def json_pointer(cls, value: str) -> str:
        if value and not value.startswith("/"):
            raise ValueError("The balance field must be a JSON pointer, for example /data/balance")
        return value
