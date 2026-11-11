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


def ensure(context: Context, selectors: list[str], *, phase: str = "all", steps: list[Step] | None = None,
           verify_after: bool = False) -> None:
    selected = plan(context, selectors) if steps is None else steps
    selected = [step for step in selected if phase == "all" or
                (step.recipe.provider == "apt") == (phase == "system")]
    if not selected:
        return
    context.root.mkdir(parents=True, exist_ok=True)
    path = context.root / "setup.json"
    with FileLock(str(context.root / "setup.lock")):
        state: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {"completed": {}}
        try:
            for step in selected:
                state["component"] = step.name
                recipe = step.recipe
                revision = fingerprint([context.architecture, asdict(recipe), context.artifacts])
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
                state["completed"][step.name] = revision
                state.pop("error", None)
                write_json(path, state)
                print(f"[setup] {step.name}: ready", flush=True)
            if verify_after:
                for step in selected:
                    state.update(status="verifying", component=step.name)
                    write_json(path, state)
                    verification = step.recipe.verify(context)
                    if not verification.ready:
                        raise RuntimeError(f"{step.name} final verification failed: {verification.reason}")
                    print(f"[setup] {step.name}: verified", flush=True)
        except Exception as error:
            state["completed"].pop(state["component"], None)
            state.update(status="failed", error=str(error))
            write_json(path, state)
            raise
        state.update(status="ready", component=None)
        state.pop("error", None)
        write_json(path, state)
