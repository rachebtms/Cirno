"""Preserve individual marketplace failures beside usable results."""

import asyncio
from collections.abc import Sequence


def marketplace_warnings(results: Sequence[object]) -> list[dict[str, str]]:
    warnings = []
    for provider, result in zip(("skills_sh", "skillhub"), results, strict=True):
        if isinstance(result, asyncio.CancelledError):
            raise result
        if isinstance(result, Exception):
            warnings.append({"provider": provider, "message": str(result)})
    return warnings


def marketplace_failure_message(warnings: list[dict[str, str]]) -> str:
    names = {"skills_sh": "skills.sh", "skillhub": "SkillHub"}
    return "; ".join(f"{names[warning['provider']]}: {warning['message']}" for warning in warnings)
