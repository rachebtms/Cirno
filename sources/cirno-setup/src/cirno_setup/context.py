"""Paths, subprocess environment and startup configuration shared by provisioners."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cirno_setup.environment import TOOL_ENV_KEYS
from cirno_setup.policy import Policy


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass
class Context:
    home: Path
    assets: Path
    policy: Policy
    proxy: str | None = None
    apt_updated: bool = False
    python_requirements: dict[str, list[str]] = field(default_factory=dict)

    @property
    def root(self) -> Path:
        return self.home / ".cirno" / "state" / "tools"

    @property
    def managed(self) -> Path:
        return self.root / "bundled"

    @property
    def architecture(self) -> str:
        return {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}[platform.machine()]

    @property
    def artifacts(self) -> dict[str, Any]:
        return json.loads((self.assets / "artifacts.json").read_text(encoding="utf-8"))

    @property
    def python(self) -> Path:
        return self.root / "python" / "bin" / "python"

    @property
    def service_python(self) -> Path:
        return Path(os.environ.get("CIRNO_SERVICE_PYTHON", sys.executable))

    def environment(self) -> dict[str, str]:
        # APT maintainer scripts must never source user-controlled BASH_ENV,
        # Python paths or persistent tool executables while running as root.
        if os.geteuid() == 0:
            env = {"PATH": "/usr/bin:/bin", "HOME": str(self.home)}
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "LANG"):
                if key in os.environ:
                    env[key] = os.environ[key]
            if self.proxy:
                env.update(HTTP_PROXY=self.proxy, HTTPS_PROXY=self.proxy, ALL_PROXY=self.proxy)
            return env
        keys = (
            *TOOL_ENV_KEYS,
            "HOME",
            "LANG",
            "TERM",
            "HOMEBREW_PREFIX",
            "HOMEBREW_NO_AUTO_UPDATE",
            "HOMEBREW_NO_ANALYTICS",
            "HOMEBREW_CACHE",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "SSL_CERT_FILE",
            "NODE_EXTRA_CA_CERTS",
            "PLAYWRIGHT_DOWNLOAD_HOST", "PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST",
            "PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT",
            "UV_INDEX_URL", "UV_EXTRA_INDEX_URL", "UV_FIND_LINKS",
            "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_FIND_LINKS",
        )
        env = {key: os.environ[key] for key in keys if key in os.environ}
        env["PATH"] = ":".join(
            [
                str(self.managed / "node" / "bin"),
                str(self.python.parent),
                str(self.root / "bin"),
                str(self.root / "npm/bin"),
                str(self.managed / "pandoc" / "bin"),
                str(self.managed / "xurl" / "bin"),
                "/opt/cirno/bin",
                "/usr/local/bin",
                "/usr/bin",
                "/bin",
                "/home/linuxbrew/.linuxbrew/bin",
                os.environ.get("PATH", ""),
            ]
        )
        if self.proxy:
            env.update(HTTP_PROXY=self.proxy, HTTPS_PROXY=self.proxy, ALL_PROXY=self.proxy)
        env.setdefault("UV_CACHE_DIR", str(self.home / ".cirno/state/cli/cache/uv"))
        env.setdefault("UV_PYTHON_INSTALL_DIR", str(self.root / "uv/python"))
        from cirno_setup.python import environment

        return environment(env)

    def run(
        self,
        arguments: list[str],
        *,
        capture: bool = False,
        env_override: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        print(f"[tools] {' '.join(arguments)}", flush=True)
        return subprocess.run(
            arguments,
            env={**self.environment(), **(env_override or {})},
            timeout=self.policy.timeout_seconds,
            check=True,
            text=True,
            capture_output=capture,
        )

    def probe(self, arguments: list[str], *, env_override: dict[str, str] | None = None) -> bool:
        result = self.inspect(arguments, env_override=env_override)
        if result.returncode:
            print(f"[tools] Check failed: {result.stderr.strip()[:500]}", flush=True)
        return result.returncode == 0

    def inspect(
        self, arguments: list[str], *, env_override: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                arguments,
                env={**self.environment(), **(env_override or {})},
                timeout=min(60, self.policy.timeout_seconds),
                text=True,
                capture_output=True,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            # A missing or broken executable is a failed readiness check. The
            # provisioner repairs it and then checks the installation again.
            print(f"[tools] Dependency check failed: {error}", flush=True)
            return subprocess.CompletedProcess(arguments, 127, stdout="", stderr=str(error))
