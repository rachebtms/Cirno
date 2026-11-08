"""Extract local path references and top-level shell command segments."""

from __future__ import annotations

import re
import shlex
from urllib.parse import unquote


def split_shell_segments(command: str) -> list[str]:
    """Split shell commands on top-level chaining operators."""
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    paren_depth = 0
    i = 0

    while i < len(command):
        ch = command[i]

        if escaped:
            current.append(ch)
            escaped = False
            i += 1
            continue

        if ch == "\\" and quote != "'":
            current.append(ch)
            escaped = True
            i += 1
            continue

        if quote is not None:
            current.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue

        if ch in {"'", '"', "`"}:
            current.append(ch)
            quote = ch
            i += 1
            continue

        if ch == "(":
            paren_depth += 1
            current.append(ch)
            i += 1
            continue

        if ch == ")" and paren_depth > 0:
            paren_depth -= 1
            current.append(ch)
            i += 1
            continue

        operator_len = 0
        if paren_depth == 0:
            if command.startswith(("&&", "||"), i):
                operator_len = 2
            elif ch == "&" and not (
                (i > 0 and command[i - 1] in "<>") or command.startswith("&>", i)
            ):
                current.append(ch)
                operator_len = 1
            # A newline separates commands just like ";" does, so a payload
            # smuggled onto its own line must be checked on its own too.
            elif ch in {";", "|", "\n", "\r"}:
                operator_len = 1

        if operator_len:
            segment = "".join(current).strip()
            if segment:
                segments.append(segment)
            current = []
            i += operator_len
            continue

        current.append(ch)
        i += 1

    segment = "".join(current).strip()
    if segment:
        segments.append(segment)
    return segments


def extract_absolute_paths(command: str) -> list[str]:
    # Windows: match drive-root paths like `C:\` as well as `C:\path\to\file`, and UNC paths like `\\server\share`
    # NOTE: `*` is required so `C:\` (nothing after the slash) is still extracted.
    win_paths = re.findall(
        r"(?<![A-Za-z])(?:[A-Za-z]:[^\s\"'|><;]*|\\\\[^\s\"'|><;]+(?:\\[^\s\"'|><;]+)*)", command
    )
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        # Keep malformed quoting fail-closed. The shell will normally reject
        # it too, but a conservative raw scan must not turn it into a bypass.
        tokens = [command]

    paths = [*win_paths]
    seen = set(win_paths)
    for index, token in enumerate(tokens):
        for path in extract_posix_paths_from_token(token):
            if path not in seen:
                paths.append(path)
                seen.add(path)
        if index > 0 and tokens[index - 1] in {"-c", "-lc", "--command"}:
            for path in extract_absolute_paths(token):
                if path not in seen:
                    paths.append(path)
                    seen.add(path)
    return paths


def extract_posix_paths_from_token(token: str) -> list[str]:
    """Extract local POSIX/home paths from one shell-decoded token.

    ``shlex`` separates real grouping/redirection operators while preserving
    parentheses and spaces that were quoted or escaped as part of a path.
    Embedded scripts (for example ``sh -c \"cat /tmp/x\"``) still need a
    small boundary scan. Colons are not general boundaries: treating them
    as such misclassifies URLs, ``host:/remote`` and ``C:/Windows``. They
    are considered only inside a syntactically valid assignment, where
    shells expand each colon-delimited tilde component.
    """
    paths: list[str] = []
    for match in re.finditer(
        r"file://(?:[^/\s\"']+)?(/[^\s\"'<>|;&]*)",
        token,
        flags=re.IGNORECASE,
    ):
        uri_prefix = token[: match.start()]
        raw_path = match.group(1)
        if uri_prefix.count("(") > uri_prefix.count(")"):
            raw_path = raw_path.split(")", 1)[0]
        if uri_prefix.count("{") > uri_prefix.count("}"):
            raw_path = raw_path.split(",", 1)[0].split("}", 1)[0]
        raw_path = raw_path.split("?", 1)[0].split("#", 1)[0]
        if raw_path:
            paths.append(unquote(raw_path))
    boundary_chars = frozenset(" \t\r\n=({,<>|;&\"'")
    i = 0
    while i < len(token):
        is_posix = token[i] == "/"
        home_match = re.match(
            r"~(?:[+-](?:\d+)?|[A-Za-z0-9_.@-]+)?(?=/|:|$)",
            token[i:],
        )
        is_home = home_match is not None
        if not is_posix and not is_home:
            i += 1
            continue

        prefix = token[:i]
        parameter_default = i >= 2 and token[i - 2] == ":" and token[i - 1] in "-+?="
        word_start = (
            max(
                (prefix.rfind(char) for char in " \t\r\n<>|;&"),
                default=-1,
            )
            + 1
        )
        word_prefix = prefix[word_start:]
        assignment_component = bool(
            re.fullmatch(
                r"(?:[A-Za-z_][A-Za-z0-9_]*|--?[A-Za-z0-9_.-]+)="
                r"(?:[^:=\s]*:)*",
                word_prefix,
            )
        )
        at_boundary = i == 0 or token[i - 1] in boundary_chars
        if is_home:
            # A shell word beginning with ``~`` is a separate shlex token.
            # Mid-token expansion is valid only after ``=`` or a colon in
            # an assignment. This avoids PromQL/Loki ``=~`` and ``|~``
            # match operators while covering PATH-like values.
            at_boundary = i == 0 or assignment_component
        if not at_boundary and not parameter_default:
            i += 1
            continue

        if re.search(r"[A-Za-z][A-Za-z0-9+.-]*://", word_prefix) or re.match(
            r"(?:[^/:=\s]+@)?[^/:=\s]+:$",
            word_prefix,
        ):
            # HTTP-style URL path/query fragments and scp-style remote paths
            # are not local filesystem references. ``file://`` paths were
            # decoded above. Windows drive paths are already captured by the
            # platform-specific expression above.
            i += 1
            continue

        assignment_value = assignment_component
        if i == 0 or assignment_value:
            end = len(token)
            if assignment_value:
                separator = token.find(":", i)
                if separator >= 0:
                    end = separator
        elif token[i - 1] in {"'", '"'}:
            quote = token[i - 1]
            closing = token.find(quote, i)
            end = len(token) if closing < 0 else closing
        else:
            end_chars = set(" \t\r\n\"'<>|;&")
            if prefix.count("(") > prefix.count(")"):
                end_chars.add(")")
            if prefix.count("{") > prefix.count("}"):
                end_chars.update({",", "}"})
            end = i
            while end < len(token) and token[end] not in end_chars:
                end += 1

        candidate = token[i:end]
        if candidate:
            paths.append(candidate)
        i = max(end, i + 1)
    return paths
