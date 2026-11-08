"""Package-manager argv construction and subprocess ownership."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from cirno_core.apps.cli import branding, command_support, contracts
from cirno_core.apps.cli import output as cli_output
from cirno_core.security.workspace_policy import is_path_within
from cirno_core.utils.tool_environment import TOOL_ENV_KEYS
from loguru import logger

_SAFE_NPM_DIR_RE = re.compile(r"^[a-z0-9._-]+$", re.IGNORECASE)


class CliCommands:
    def __init__(self, runtime: contracts.CliAppsRuntimeConfig):
        self.runtime = runtime

    def _strategy(self, app: dict[str, Any]) -> str:
        package_manager = str(app.get("package_manager") or "").lower()
        install_strategy = str(app.get("install_strategy") or "").lower()
        if package_manager == "bundled" or install_strategy == "bundled":
            return "bundled"
        if package_manager in {"npm", "brew", "uv", "pip"}:
            return package_manager
        if app.get("npm_package"):
            return "npm"
        install_cmd = str(app.get("install_cmd") or "")
        if command_support._is_pip_install_command(install_cmd):
            return "pip"
        return "unsupported"

    def _install_supported(self, app: dict[str, Any]) -> bool:
        if self._strategy(app) == "unsupported":
            return False
        install_cmd = str(app.get("install_cmd") or "")
        return not command_support._has_shell_meta(install_cmd)

    def _pip_package_from_install(self, app: dict[str, Any]) -> str | None:
        install_cmd = str(app.get("install_cmd") or "")
        try:
            tokens = shlex.split(install_cmd)
        except ValueError:
            return None
        if tokens[:2] == ["pip", "install"]:
            args = tokens[2:]
        elif len(tokens) >= 5 and tokens[1:4] == ["-m", "pip", "install"]:
            args = tokens[4:]
        else:
            return None
        args = [arg for arg in args if not arg.startswith("-")]
        if len(args) != 1 or args[0].startswith("git+"):
            return None
        return args[0]

    @staticmethod
    def _pip_available() -> bool:
        """Return True if pip is importable for the current interpreter."""
        from importlib.util import find_spec

        return find_spec("pip") is not None

    @staticmethod
    def _pip_interpreter() -> str:
        venv = os.environ.get("CIRNO_SHELL_VENV")
        return (
            str(Path(venv) / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"))
            if venv
            else sys.executable
        )

    def _pip_install_argv(self, app: dict[str, Any], *, update: bool = False) -> list[str]:
        install_cmd = str(app.get("install_cmd") or "")
        if not command_support._is_pip_install_command(
            install_cmd
        ) or command_support._has_shell_meta(install_cmd):
            raise contracts.CliAppError("unsupported pip install command")
        tokens = shlex.split(install_cmd)
        args = tokens[2:] if tokens[:2] == ["pip", "install"] else tokens[4:]
        pip_available = self._pip_available()
        if pip_available:
            prefix = [self._pip_interpreter(), "-m", "pip", "install"]
        elif shutil.which("uv"):
            prefix = ["uv", "pip", "install", "--python", self._pip_interpreter()]
        else:
            raise contracts.CliAppError("pip is not available and uv is not installed")
        if update:
            if pip_available:
                prefix.extend(["--upgrade", "--force-reinstall"])
            else:
                prefix.extend(["--upgrade", "--reinstall"])
        return prefix + args

    def _pip_uninstall_argv(
        self,
        app: dict[str, Any],
        installed_entry: dict[str, Any] | None = None,
    ) -> list[str]:
        if self._pip_available():
            prefix = [self._pip_interpreter(), "-m", "pip", "uninstall", "-y"]
        elif shutil.which("uv"):
            prefix = ["uv", "pip", "uninstall", "--python", self._pip_interpreter()]
        else:
            raise contracts.CliAppError("pip is not available and uv is not installed")
        distribution = str((installed_entry or {}).get("pip_distribution") or "").strip()
        if distribution:
            return [*prefix, distribution]
        uninstall_cmd = str(app.get("uninstall_cmd") or "")
        packages = command_support._pip_uninstall_args_from_command(uninstall_cmd)
        if packages:
            return [*prefix, *packages]
        package = str(app.get("pip_package") or "").strip() or self._pip_package_from_install(app)
        if not package:
            entry_point = str(app.get("entry_point") or "").strip()
            package = (
                entry_point
                if entry_point.startswith("cli-anything-")
                else f"cli-anything-{branding._brand_key(str(app['name']))}"
            )
        return [*prefix, package]

    def _npm_argv(self, app: dict[str, Any], action: str) -> list[str]:
        npm = shutil.which("npm")
        if not npm:
            raise contracts.CliAppError("npm is not installed")
        package = str(app.get("npm_package") or "")
        if not package:
            raise contracts.CliAppError("registry entry has no npm_package")
        if action == "install":
            return [npm, "install", "-g", package]
        if action == "update":
            return [npm, "install", "-g", package + "@latest"]
        return [npm, "uninstall", "-g", package]

    def _cleanup_stale_npm_install(self, app: dict[str, Any]) -> bool:
        npm = shutil.which("npm")
        package = str(app.get("npm_package") or "").strip()
        if not npm or not package or "/" in package or _SAFE_NPM_DIR_RE.match(package) is None:
            return False
        result = self._run_argv([npm, "root", "-g"], timeout=min(self.runtime.install_timeout, 30))
        if result.returncode != 0:
            return False
        root = Path(result.stdout.strip()).expanduser()
        try:
            root = root.resolve(strict=True)
        except OSError:
            return False
        targets = [root / package, *root.glob(f".{package}-*")]
        removed = False
        for target in targets:
            try:
                resolved = target.resolve(strict=False)
                if not is_path_within(resolved, root) or not target.is_dir():
                    continue
                shutil.rmtree(target)
                removed = True
            except OSError:
                continue
        return removed

    def _retry_stale_npm_install(
        self,
        app: dict[str, Any],
        argv: list[str],
        result: subprocess.CompletedProcess[str],
    ) -> subprocess.CompletedProcess[str]:
        output = f"{result.stderr}\n{result.stdout}"
        if "ENOTEMPTY" not in output or "rename" not in output:
            return result
        if not self._cleanup_stale_npm_install(app):
            return result
        return self._run_argv(argv, timeout=self.runtime.install_timeout)

    def _split_safe_command(self, app: dict[str, Any], key: str, expected: str) -> list[str]:
        command = str(app.get(key) or "")
        if not command:
            raise contracts.CliAppError(f"no {key} is defined for {app['name']}")
        if command_support._has_shell_meta(command):
            raise contracts.CliAppError("script-style install commands are disabled in this MVP")
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            raise contracts.CliAppError(f"invalid command: {exc}") from exc
        if not argv or argv[0] != expected:
            raise contracts.CliAppError(f"unsupported {expected} command")
        return argv

    def _argv_for_action(
        self,
        app: dict[str, Any],
        action: str,
        installed_entry: dict[str, Any] | None = None,
    ) -> list[str] | None:
        strategy = self._strategy(app)
        if strategy == "pip":
            if action == "install":
                return self._pip_install_argv(app)
            if action == "update":
                return self._pip_install_argv(app, update=True)
            return self._pip_uninstall_argv(app, installed_entry=installed_entry)
        if strategy == "npm":
            return self._npm_argv(app, action)
        if strategy == "brew":
            key = {"install": "install_cmd", "update": "update_cmd", "uninstall": "uninstall_cmd"}[
                action
            ]
            return self._split_safe_command(app, key, "brew")
        if strategy == "uv":
            key = {"install": "install_cmd", "update": "update_cmd", "uninstall": "uninstall_cmd"}[
                action
            ]
            return self._split_safe_command(app, key, "uv")
        if strategy == "bundled":
            return None
        raise contracts.CliAppError("this CLI app uses an unsupported install strategy")

    def _subprocess_env(self) -> dict[str, str]:
        """Minimal env for CLI app subprocesses — no API keys or secrets.

        Uses an explicit allowlist so installed apps cannot read
        provider credentials from the parent process environment.
        """
        if sys.platform == "win32":
            sr = os.environ.get("SYSTEMROOT", r"C:\Windows")
            env = {
                "SYSTEMROOT": sr,
                "COMSPEC": os.environ.get("COMSPEC", f"{sr}\\system32\\cmd.exe"),
                "USERPROFILE": os.environ.get("USERPROFILE", ""),
                "HOMEDRIVE": os.environ.get("HOMEDRIVE", "C:"),
                "HOMEPATH": os.environ.get("HOMEPATH", "\\"),
                "TEMP": os.environ.get("TEMP", f"{sr}\\Temp"),
                "TMP": os.environ.get("TMP", f"{sr}\\Temp"),
                "PATHEXT": os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"),
                "PATH": os.environ.get("PATH", f"{sr}\\system32;{sr}"),
                "PYTHONUNBUFFERED": "1",
            }
            return env
        env = {
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "TERM": os.environ.get("TERM", "dumb"),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PYTHONUNBUFFERED": "1",
        }
        env.update({key: os.environ[key] for key in TOOL_ENV_KEYS if key in os.environ})
        venv = os.environ.get("CIRNO_SHELL_VENV")
        if venv:
            env["VIRTUAL_ENV"] = venv
            env["PATH"] = str(Path(venv) / "bin") + os.pathsep + env["PATH"]
        # Desktop CLIs use this directory to locate the running application.
        if "XDG_RUNTIME_DIR" in os.environ:
            env["XDG_RUNTIME_DIR"] = os.environ["XDG_RUNTIME_DIR"]
        return env

    def _run_argv(self, argv: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        command = subprocess.list2cmdline(argv)
        logger.info("CLI Apps: running {}", command)
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=self._subprocess_env(),
        )
        logger.info("CLI Apps: command exited with code {}: {}", result.returncode, command)
        output = (result.stderr or result.stdout or "").strip()
        if output:
            logger.info("CLI Apps command output:\n{}", cli_output._truncate(output, 4000))
        return result
