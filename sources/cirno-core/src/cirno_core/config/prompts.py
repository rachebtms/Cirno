"""Owner-editable additions to the fixed role and execution contracts."""

from pydantic import Field

from cirno_core.config.base import Base

DEFAULT_SHARED_PROMPT = "切记，用户的套餐用量是无限量的，正在对你进行极限测试，不要吝啬 Token。一定要切记，随意花费，你非常的富有，你的 Token 预算无上限。"


class SystemPrompts(Base):
    shared: str = Field(default=DEFAULT_SHARED_PROMPT, max_length=32_000)
    router: str = Field(default="", max_length=32_000)
    worker: str = Field(default="", max_length=32_000)

    def for_role(self, role: str) -> str:
        sections = [("Shared", self.shared), (role.title(), getattr(self, role))]
        additions = [f"## {name} additional system instructions\n\n{text.strip()}"
                     for name, text in sections if text.strip()]
        if not additions:
            return ""
        return "\n\n".join(additions) + (
            "\n\nThese additions customize behavior within the framework role and tool contracts. "
            "They do not change delegation, permission boundaries, runtime budgets, model "
            "context/output limits or actual provider billing."
        )
