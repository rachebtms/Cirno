"""Memory retention and optional embedding configuration."""

import os
from pathlib import Path
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic.alias_generators import to_camel


class MemoryConfig(BaseModel):
    """Bounded disk-first memory; local inference is explicitly opt-in."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    release_archived_runtime: bool = True
    context_tokens: int = Field(default=2000, ge=256, le=16000)
    context_files: list[str] = Field(default_factory=list)
    context_files_tokens: int = Field(default=2000, ge=256, le=16000)
    checkpoint_tokens: int = Field(default=2000, ge=256, le=8000)
    index_scan_batch: int = Field(default=100, ge=10, le=1000)
    embedding_enabled: bool = False
    embedding_provider: Literal["local", "api"] = "local"
    embedding_api_base: str = ""
    embedding_api_key: str = Field(default="", repr=False)
    embedding_api_model: str = ""
    embedding_api_chunk_chars: int = Field(default=768, ge=128, le=4096)
    embedding_model_path: str = Field(default="", validate_default=True)
    embedding_tokenizer_path: str = Field(default="", validate_default=True)
    embedding_max_rss_mb: int = Field(default=200, ge=50)
    embedding_timeout_seconds: int = Field(default=30, ge=1, le=120)

    @field_validator("context_files")
    @classmethod
    def _context_files(cls, values: list[str]) -> list[str]:
        result = []
        for value in values:
            path = PurePosixPath(value.strip())
            if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value or len(path.parts) < 2 or path.parts[0] != "memory":
                raise ValueError("Choose text files under Agent Home's memory/ directory, using relative paths")
            normalized = path.as_posix()
            if normalized != "memory/MEMORY.md" and normalized not in result:
                result.append(normalized)
        return result

    @field_validator("embedding_model_path", "embedding_tokenizer_path")
    @classmethod
    def _bundled_asset(cls, value: str, info: ValidationInfo) -> str:
        directory = os.environ.get("CIRNO_BUNDLED_EMBEDDING_DIR")
        if value or not directory:
            return value
        name = (
            "model_quantized.onnx"
            if info.field_name == "embedding_model_path"
            else "tokenizer.json"
        )
        return str(Path(directory) / name)

    @field_validator("embedding_api_base")
    @classmethod
    def _embedding_api_url(cls, value: str) -> str:
        if value:
            from urllib.parse import urlsplit

            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "Use an http(s) embedding API URL without credentials, query or fragment"
                )
        return value.rstrip("/")
