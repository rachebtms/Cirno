"""Validated remote shell setup shared by SSH credentials and Nodes."""

import re

from pydantic import BaseModel, Field, field_validator


class SSHSessionSettings(BaseModel):
    working_directory: str = Field(default=".", min_length=1)
    init_script: str = ""
    environment: dict[str, str] = Field(default_factory=dict)

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, values: dict[str, str]) -> dict[str, str]:
        for name, value in values.items():
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None or "\0" in value:
                raise ValueError("Environment variables need shell variable names and values without NUL bytes")
        return values
