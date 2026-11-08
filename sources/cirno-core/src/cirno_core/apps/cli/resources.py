"""Catalog origins and raw Skill sources."""

from __future__ import annotations

CLI_ANYTHING_REGISTRY_URL = "https://hkuds.github.io/CLI-Anything/registry.json"


CLI_ANYTHING_PUBLIC_REGISTRY_URL = "https://hkuds.github.io/CLI-Anything/public_registry.json"


CLI_ANYTHING_RAW_BASE = "https://raw.githubusercontent.com/HKUDS/CLI-Anything/main"


CIRNO_EXTENSION_REGISTRY_URL = (
    "https://raw.githubusercontent.com/Re-bin/nanobot-extension/main/registry.json"
)


CIRNO_EXTENSION_RAW_BASE = "https://raw.githubusercontent.com/Re-bin/nanobot-extension/main"


_CATALOG_SOURCES = (
    ("harness", CLI_ANYTHING_REGISTRY_URL, CLI_ANYTHING_RAW_BASE, True),
    ("public", CLI_ANYTHING_PUBLIC_REGISTRY_URL, CLI_ANYTHING_RAW_BASE, True),
    ("extensions", CIRNO_EXTENSION_REGISTRY_URL, CIRNO_EXTENSION_RAW_BASE, False),
)
