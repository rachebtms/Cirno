"""Catalog branding and display descriptions."""

from __future__ import annotations

import re
from typing import Any

_SAFE_NAME_RE = re.compile(r"[^a-z0-9_-]+")


_ENDORSEMENT_WORD_RE = re.compile(r"\bofficial\s+", re.IGNORECASE)


_BRANDS: dict[str, tuple[str, str]] = {
    "1password-cli": ("1password", "#3B66BC"),
    "arcgis": ("arcgis", "#2C7AC3"),
    "arcgis-pro": ("arcgis", "#2C7AC3"),
    "audacity": ("audacity", "#0000CC"),
    "blender": ("blender", "#E87D0D"),
    "browser": ("googlechrome", "#4285F4"),
    "calibre": ("calibre", "#45B29D"),
    "chromadb": ("chroma", "#FFDE2D"),
    "comfyui": ("comfyui", "#111827"),
    "contentful": ("contentful", "#2478CC"),
    "dify": ("dify", "#155EEF"),
    "drawio": ("diagramsdotnet", "#F08705"),
    "elevenlabs": ("elevenlabs", "#000000"),
    "eth2-quickstart": ("ethereum", "#627EEA"),
    "firefly-iii": ("fireflyiii", "#CD5029"),
    "freecad": ("freecad", "#418FDE"),
    "generate-veo-video": ("googlegemini", "#8E75B2"),
    "gimp": ("gimp", "#5C5543"),
    "godot": ("godotengine", "#478CBF"),
    "hacker-feeds-cli": ("rss", "#FFA500"),
    "inkscape": ("inkscape", "#000000"),
    "intelwatch": ("intel", "#0071C5"),
    "iterm2": ("iterm2", "#000000"),
    "jimeng": ("bytedance", "#3C8CFF"),
    "joplin": ("joplin", "#1071D3"),
    "kdenlive": ("kdenlive", "#527EB2"),
    "krita": ("krita", "#3BABFF"),
    "libreoffice": ("libreoffice", "#18A303"),
    "mailchimp": ("mailchimp", "#FFE01B"),
    "mermaid": ("mermaid", "#FF3670"),
    "minimax": ("minimax", "#111827"),
    "musescore": ("musescore", "#1A70B8"),
    "n8n": ("n8n", "#EA4B71"),
    "notebooklm": ("googlenotebooklm", "#4285F4"),
    "obs-studio": ("obsstudio", "#302E31"),
    "obsidian": ("obsidian", "#7C3AED"),
    "ollama": ("ollama", "#000000"),
    "pm2": ("pm2", "#2B037A"),
    "qgis": ("qgis", "#589632"),
    "safari": ("safari", "#006CFF"),
    "sanity": ("sanity", "#F03E2F"),
    "sentry": ("sentry", "#362D59"),
    "sketch": ("sketch", "#F7B500"),
    "shopify": ("shopify", "#7AB55C"),
    "nsight-graphics": ("nvidia", "#76B900"),
    "unrealinsights": ("unrealengine", "#0E1128"),
    "ueatelier": ("unrealengine", "#0E1128"),
    "ve-twini": ("x", "#000000"),
    "wecom": ("wechat", "#07C160"),
    "suno": ("suno", "#000000"),
    "lldb": ("llvm", "#262D3A"),
    "android-cli": ("android", "#3DDC84"),
    "adguardhome": ("adguard", "#68BC71"),
    "zotero": ("zotero", "#CC2936"),
    "zoom": ("zoom", "#0B5CFF"),
}


_BRAND_DOMAINS: dict[str, tuple[str, str]] = {
    "3mf": ("3mf.io", "#00A1DE"),
    "anygen": ("anygen.io", "#111827"),
    "clibrowser": ("github.com/allthingssecurity/clibrowser", "#24292F"),
    "cloudanalyzer": ("github.com/rsasaki0109/CloudAnalyzer", "#2563EB"),
    "cloudcompare": ("cloudcompare.org", "#4D83C3"),
    "deployhq": ("deployhq.com", "#00A2D9"),
    "exa": ("exa.ai", "#111827"),
    "feishu": ("larksuite.com", "#00A5FF"),
    "inkstitch": ("inkstitch.org", "#222222"),
    "macrocli": ("github.com/HKUDS/CLI-Anything/tree/main/macrocli", "#24292F"),
    "mubu": ("mubu.com", "#16A085"),
    "nslogger": ("github.com/fpillet/NSLogger", "#24292F"),
    "novita": ("novita.ai", "#7C3AED"),
    "openscreen": ("openscreen.com", "#2563EB"),
    "py4csr": ("github.com/yanmingyu92/py4csr", "#24292F"),
    "quietshrink": ("github.com/achiya-automation/quietshrink", "#111827"),
    "renderdoc": ("renderdoc.org", "#2C7DB8"),
    "rms": ("rms.teltonika-networks.com", "#0054A6"),
    "sbox": ("sbox.game", "#F59E0B"),
    "seaclip": ("github.com/SeaClip-Lite/SeaClip", "#0284C7"),
    "shotcut": ("shotcut.org", "#3B82F6"),
    "slay-the-spire-ii": ("megacrit.com", "#B91C1C"),
    "stata": ("stata.com", "#1F4E79"),
    "unimol-tools": ("github.com/deepmodeling/Uni-Mol", "#4F46E5"),
    "videocaptioner": ("github.com/WEIFENG2333/VideoCaptioner", "#2563EB"),
    "wiremock": ("wiremock.org", "#FF6A00"),
}


_BRAND_ALIASES: dict[str, str] = {
    "1password": "1password-cli",
    "dify-workflow": "dify",
    "feishu-lark": "feishu",
    "lark-cli": "feishu",
    "minimax-cli": "minimax",
    "obsidian-cli": "obsidian",
    "obsidian-agent": "obsidian",
    "obsidian-agent-cli": "obsidian",
    "slay-the-spire-2": "slay-the-spire-ii",
    "slay-the-spire-ii": "slay-the-spire-ii",
    "unimol-tools": "unimol-tools",
    "unimol": "unimol-tools",
    "veo": "generate-veo-video",
}


_BRAND_TRAILING_WORDS = ("cli", "workflow", "workflows", "app", "apps", "tool", "tools")


def _brand_key(value: str) -> str:
    return _SAFE_NAME_RE.sub("-", value.lower()).replace("_", "-").strip("-")


def _brand_candidates(app: dict[str, Any]) -> list[str]:
    values = [
        str(app.get("name") or ""),
        str(app.get("display_name") or ""),
        str(app.get("entry_point") or "").removeprefix("cli-anything-"),
    ]
    seen: set[str] = set()
    candidates: list[str] = []
    for value in values:
        key = _brand_key(value)
        while key and key not in seen:
            seen.add(key)
            candidates.append(key)
            parts = key.split("-")
            if len(parts) <= 1 or parts[-1] not in _BRAND_TRAILING_WORDS:
                break
            key = "-".join(parts[:-1])
    return candidates


def _brand_payload(app: dict[str, Any]) -> tuple[str | None, str | None]:
    declared_logo = str(app.get("logo_url") or "").strip()
    if declared_logo.startswith(("https://", "/")):
        declared_color = str(app.get("brand_color") or "").strip()
        return declared_logo, declared_color or None

    brand = None
    domain_brand = None
    for candidate in _brand_candidates(app):
        key = _BRAND_ALIASES.get(candidate, candidate)
        brand = _BRANDS.get(key)
        if brand:
            break
        domain_brand = _BRAND_DOMAINS.get(key)
        if domain_brand:
            break
    if not brand:
        if not domain_brand:
            return None, None
        domain, color = domain_brand
        return f"https://www.google.com/s2/favicons?domain={domain}&sz=64", color
    slug, color = brand
    return f"https://cdn.simpleicons.org/{slug}/{color.lstrip('#')}", color


def _catalog_description(app: dict[str, Any]) -> str:
    """Return catalog copy without implying vendor endorsement."""
    description = str(app.get("description") or "")
    return _ENDORSEMENT_WORD_RE.sub("", description).strip()
