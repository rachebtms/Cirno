"""Typed learning output appended to a replayable task checkpoint."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MARKER = "\n## Memory updates\n"


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    message: int | None = Field(default=None, ge=0)
    memory_id: str | None = None
    source_id: str | None = Field(default=None, min_length=1, max_length=160)
    quote: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def one_source(self):
        if sum(value is not None for value in (self.message, self.memory_id, self.source_id)) > 1:
            raise ValueError("Evidence must not combine source_id, message and memory_id")
        if self.source_id is None and self.quote is None:
            raise ValueError("Legacy evidence requires an exact quote")
        # A quote without an index must resolve to exactly one archived message.
        return self


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    content: str = Field(min_length=1, max_length=6000)
    kind: Literal["fact", "observation", "hypothesis", "lesson"]
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=8)
    supersedes: str | None = None


class DocumentEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    content: str = Field(min_length=1, max_length=16000)
    evidence: list[EvidenceRef] = Field(min_length=1, max_length=8)
    # A new autonomous Skill needs evidence from another independent task.
    related_memory_ids: list[str] = Field(default_factory=list, max_length=8)


class InputReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    memory_id: str
    reason: str = Field(min_length=1, max_length=2000)


class LearningPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    memories: list[Finding] = Field(default_factory=list, max_length=32)
    documents: list[DocumentEdit] = Field(default_factory=list, max_length=32)

    reviewed_inputs: list[InputReview] = Field(default_factory=list, max_length=32)

    @property
    def size(self) -> int:
        return len(self.memories) + len(self.documents)


def split_result(text: str) -> tuple[str, LearningPlan]:
    """No update section means there was no useful durable learning.

    Once the model supplies a section it must be valid; malformed plans are
    never repaired, executed as tools, or replayed as task instructions.
    """
    summary, marker, payload = text.partition(MARKER)
    if not marker:
        return summary, LearningPlan()
    payload = payload.strip()
    if payload.startswith("```json\n") and payload.endswith("```"):
        payload = payload[8:-3].strip()
    return summary, LearningPlan.model_validate(json.loads(payload))
