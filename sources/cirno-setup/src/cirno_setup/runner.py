"""Serial setup execution with per-recipe verification and durable checkpoints."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

from filelock import FileLock

from cirno_setup.apt import write_json
from cirno_setup.context import Context, fingerprint
from cirno_setup.planner import Step, plan


def ensure(context: Context, selectors: list[str], *, phase: str = "all", steps: list[Step] | None = None) -> None:
    selected = plan(context, selectors) if steps is None else steps
    selected = [step for step in selected if phase == "all" or
                (step.recipe.provider == "apt") == (phase == "system")]
    if not selected:
        return
    context.root.mkdir(parents=True, exist_ok=True)
    path = context.root / "setup.json"
    with FileLock(str(context.root / "setup.lock")):
        state: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {"completed": {}}
        for step in selected:
            recipe = step.recipe
            revision = fingerprint([context.architecture, asdict(recipe), context.artifacts])
            try:
                verification = recipe.verify(context)
                if verification.ready:
                    state["completed"][step.name] = revision
                    print(f"[setup] {step.name}: ready (reused)", flush=True)
                    continue
                if recipe.provider == "apt" and os.geteuid() != 0:
                    raise PermissionError(f"{step.name} needs system installation; run the system setup phase as root")
                if recipe.provider != "apt" and os.geteuid() == 0:
                    raise PermissionError(f"{step.name} must be installed as the normal Cirno user")
                state.update(status="installing", component=step.name, reason=verification.reason)
                write_json(path, state)
                recipe.install(context)
                verification = recipe.verify(context)
                if not verification.ready:
                    raise RuntimeError(f"{step.name} verification failed: {verification.reason}")
            except Exception as error:
                state.update(status="failed", component=step.name, error=str(error))
                write_json(path, state)
                raise
            state["completed"][step.name] = revision
            state.pop("error", None)
            write_json(path, state)
            print(f"[setup] {step.name}: ready", flush=True)
        state.update(status="ready", component=None)
        state.pop("error", None)
        write_json(path, state)
