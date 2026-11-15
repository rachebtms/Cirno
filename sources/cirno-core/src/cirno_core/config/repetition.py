"""User-configurable bounds on repeated model output."""

from pydantic import Field, field_validator

from cirno_core.config.base import Base


class OutputRepetitionConfig(Base):
    enabled: bool = True
    repeat_count: int = Field(default=4, ge=3, le=20)
    max_interventions: int = Field(default=2, ge=1, le=10)
    guidance: str = Field(
        default=(
            "Your output was interrupted because it repeated the same text consecutively. "
            "Do not repeat that text or completed operations. Review the latest request and tool results, "
            "then take one useful next action or give a concise new answer. If no authorized work remains "
            "until another user request, pause or stop your own Goal with goals__update; saying that you "
            "stopped does not stop automatic continuation. Do not resume or create a Goal on your own."
        ), min_length=1, max_length=8000,
    )

    @field_validator("guidance")
    @classmethod
    def nonblank_guidance(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Repeated-output guidance must not be blank")
        return value
