"""Command-line-only setup selections and optional service startup."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from cirno_setup import apt
from cirno_setup.context import Context
from cirno_setup.initialize import initialize
from cirno_setup.planner import plan
from cirno_setup.policy import Policy
from cirno_setup.registry import catalogue
from cirno_setup.runner import ensure
from cirno_setup.system import hand_over_state, prepare


def nonnegative_seconds(value: str) -> int:
    seconds = int(value)
    if seconds < 0:
        raise argparse.ArgumentTypeError("timeout must be zero or positive seconds")
    return seconds


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="cirno-setup", description="Install +components and optionally start Cirno; put server arguments after --")
    result.add_argument("components", nargs="*")
    result.add_argument("--timeout", type=nonnegative_seconds, default=apt.DEFAULT_TIMEOUT, metavar="SECONDS",
                        help=f"Per-command timeout in seconds; 0 disables install/check time limits (default: {apt.DEFAULT_TIMEOUT})")
    result.add_argument("--no-restore-apt", action="store_true", help="Do not restore manually installed system packages")
    result.add_argument("--proxy", help="Proxy for dependency downloads")
    result.add_argument("--serve", action="store_true", help="Start Cirno after all environment checks succeed")
    result.add_argument("--verify", action="store_true", help="Recheck every selected dependency after all installations complete")
    result.add_argument("--phase", choices=("all", "system", "user"), default="all")
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--list", action="store_true")
    result.add_argument("--json", action="store_true")
    result.add_argument("--record-apt", action="store_true", help=argparse.SUPPRESS)
    result.add_argument("--snapshot-base", help=argparse.SUPPRESS)
    return result


def main(argv: list[str] | None = None) -> int:
    original = list(sys.argv[1:] if argv is None else argv)
    separator = original.index("--") if "--" in original else len(original)
    arguments = parser().parse_args(original[:separator])
    server_arguments = original[separator + 1:]
    if arguments.serve and arguments.phase != "all":
        parser().error("--serve manages both setup phases; do not combine it with --phase")
    if server_arguments and not arguments.serve:
        parser().error("server arguments after -- require --serve")
    if arguments.list:
        entries = [{"id": name, "description": recipe.description, "provider": recipe.provider,
                    "depends": list(recipe.dependencies)} for name, recipe in catalogue().items()]
        print(json.dumps(entries) if arguments.json else "\n".join(f"+{item['id']}: {item['description']}" for item in entries))
        return 0
    context = Context(Path(os.environ.get("HOME", str(Path.home()))), Path(__file__).parent / "assets",
                      Policy(restore_apt=not arguments.no_restore_apt, timeout_seconds=arguments.timeout), arguments.proxy)
    if arguments.snapshot_base:
        apt.snapshot_base(Path(arguments.snapshot_base))
        return 0
    if arguments.record_apt:
        apt.record(context)
        return 0
    selections = arguments.components
    steps = plan(context, selections)
    if arguments.dry_run:
        print(json.dumps([{"id": step.name, "provider": step.recipe.provider,
                           "depends": step.recipe.dependencies, "packages": step.recipe.packages}
                          for step in steps], indent=2))
        return 0
    if arguments.serve and os.geteuid() == 0:
        from cirno_setup import launch

        launch.prepare_home(context)
        try:
            prepare(context, steps)
            ensure(context, selections, phase="system", steps=steps)
        finally:
            hand_over_state(context)
        launch.as_user(context, original)
        return 0
    if arguments.phase == "system" or os.geteuid() == 0:
        if arguments.phase != "system" and any(step.recipe.provider != "apt" for step in steps):
            raise PermissionError("Run user-space setup as the normal user, after the root system phase")
        if os.geteuid() != 0:
            raise PermissionError("The system phase requires root")
        try:
            prepare(context, steps)
            ensure(context, selections, phase="system", steps=steps, verify_after=arguments.verify)
        finally:
            hand_over_state(context)
    else:
        initialize(context)
        ensure(context, selections, phase=arguments.phase, steps=steps, verify_after=arguments.verify)
        if arguments.serve:
            from cirno_setup.launch import start_service

            start_service(context, server_arguments)
    return 0
