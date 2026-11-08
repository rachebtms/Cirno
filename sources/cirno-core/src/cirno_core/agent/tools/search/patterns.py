"""Path queries, bounded brace globs and file type aliases."""

import fnmatch
import re
from functools import lru_cache
from pathlib import PurePosixPath

_TYPE_GLOB_MAP = {
    "py": ("*.py", "*.pyi"),
    "python": ("*.py", "*.pyi"),
    "js": ("*.js", "*.jsx", "*.mjs", "*.cjs"),
    "ts": ("*.ts", "*.tsx", "*.mts", "*.cts"),
    "tsx": ("*.tsx",),
    "jsx": ("*.jsx",),
    "json": ("*.json",),
    "md": ("*.md", "*.mdx"),
    "markdown": ("*.md", "*.mdx"),
    "go": ("*.go",),
    "rs": ("*.rs",),
    "rust": ("*.rs",),
    "java": ("*.java",),
    "sh": ("*.sh", "*.bash"),
    "yaml": ("*.yaml", "*.yml"),
    "yml": ("*.yaml", "*.yml"),
    "toml": ("*.toml",),
    "sql": ("*.sql",),
    "html": ("*.html", "*.htm"),
    "css": ("*.css", "*.scss", "*.sass"),
}


def _normalize_pattern(pattern: str) -> str:
    return pattern.strip().replace("\\", "/")


@lru_cache(maxsize=128)
def glob_patterns(pattern: str) -> tuple[str, ...]:
    """Expand bounded brace alternatives before matching path segments."""
    pending = [_normalize_pattern(pattern)]
    expanded: list[str] = []
    while pending:
        current = pending.pop()
        braces = re.search(r"\{([^{}]*)\}", current)
        if braces is None:
            if "{" in current or "}" in current:
                raise ValueError("Invalid glob: unbalanced braces")
            expanded.append(current)
            continue
        options = braces[1].split(",")
        if len(options) < 2:
            raise ValueError("Invalid glob: braces require comma-separated alternatives")
        if len(expanded) + len(pending) + len(options) > 64:
            raise ValueError("Invalid glob: at most 64 brace alternatives are supported")
        pending.extend(
            current[: braces.start()] + part + current[braces.end() :] for part in options
        )
    return tuple(expanded)


def matches_glob(rel_path: str, name: str, pattern: str) -> bool:
    return any(_match_path_glob(rel_path, name, item) for item in glob_patterns(pattern))


def _match_path_glob(rel_path: str, name: str, normalized: str) -> bool:
    if not normalized:
        return False
    if "/" in normalized:
        pattern_parts = PurePosixPath(normalized).parts
        path_parts = PurePosixPath(rel_path).parts
        matched = [True] + [False] * len(path_parts)
        for part in pattern_parts:
            if part == "**":
                # A globstar consumes zero or more complete path segments.
                for index in range(1, len(matched)):
                    matched[index] = matched[index] or matched[index - 1]
            else:
                matched = [False] + [
                    matched[index] and fnmatch.fnmatchcase(path_part, part)
                    for index, path_part in enumerate(path_parts)
                ]
        return matched[-1]
    return fnmatch.fnmatch(name, normalized)


def matches_type(name: str, file_type: str | None) -> bool:
    if not file_type:
        return True
    lowered = file_type.strip().lower()
    if not lowered:
        return True
    patterns = _TYPE_GLOB_MAP.get(lowered, (f"*.{lowered}",))
    return any(fnmatch.fnmatch(name.lower(), pattern.lower()) for pattern in patterns)


def matches_query(rel_path: str, query: str | None) -> bool:
    if not query:
        return True
    haystack = rel_path.lower()
    terms = [part for part in query.lower().split() if part]
    return all(term in haystack for term in terms)
