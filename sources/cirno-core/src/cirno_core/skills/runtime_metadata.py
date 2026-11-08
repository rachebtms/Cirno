"""One runtime contract for Skill requirements, activation and setup hints."""

from __future__ import annotations

import json
from typing import Annotated, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)

RequirementName = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)
]


class SkillMetadataError(ValueError):
    """The Skill declares runtime metadata that cannot be interpreted."""


class SkillRequirements(BaseModel):
    model_config = ConfigDict(strict=True)

    bins: list[RequirementName] = Field(default_factory=list)
    env: list[RequirementName] = Field(default_factory=list)

    @field_validator("bins", "env", mode="before")
    @classmethod
    def _optional_list(cls, value: object) -> object:
        return [] if value is None else value


class SkillRuntimeMetadata(BaseModel):
    model_config = ConfigDict(strict=True)

    requires: SkillRequirements = Field(default_factory=SkillRequirements)
    always: bool = False
    install: list[dict[str, object]] = Field(default_factory=list)

    @field_validator("requires", mode="before")
    @classmethod
    def _optional_requirements(cls, value: object) -> object:
        return {} if value is None else value

    @field_validator("install", mode="before")
    @classmethod
    def _optional_install(cls, value: object) -> object:
        return [] if value is None else value


def parse_runtime_metadata(frontmatter: dict[str, object]) -> SkillRuntimeMetadata:
    """Read cirno/openclaw extensions without turning invalid declarations into defaults."""
    raw = frontmatter.get("metadata")
    if raw is None:
        raw = {}
    if isinstance(raw, str):
        try:
            raw = cast(object, json.loads(raw))
        except json.JSONDecodeError as error:
            raise SkillMetadataError(
                f"metadata: invalid JSON at line {error.lineno}, column {error.colno}"
            ) from error
    if not isinstance(raw, dict):
        raise SkillMetadataError("metadata: expected an object")
    extensions = cast(dict[str, object], raw)
    namespace = "cirno" if "cirno" in extensions or "openclaw" not in extensions else "openclaw"
    payload = extensions.get(namespace, {})
    if not isinstance(payload, dict):
        raise SkillMetadataError(f"metadata.{namespace}: expected an object")
    values = dict(cast(dict[str, object], payload))
    root_always = "always" not in values and "always" in frontmatter
    values.setdefault("always", frontmatter.get("always", False))
    try:
        return SkillRuntimeMetadata.model_validate(values)
    except ValidationError as error:
        details = "; ".join(
            (
                "always"
                if root_always and issue["loc"] == ("always",)
                else f"metadata.{namespace}." + ".".join(map(str, issue["loc"]))
            )
            + f": {issue['msg']}"
            for issue in error.errors(include_input=False)
        )
        raise SkillMetadataError(details) from error
