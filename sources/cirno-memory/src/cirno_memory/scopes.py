"""Canonical visibility identity, independent of a record's originating chat."""


def scope_identity(record: dict) -> tuple[str, str | None]:
    scope = record["scope"]
    return scope, record.get("project_id") if scope == "project" else record.get("session_key") if scope == "session" else None


def visible(record: dict, session_key: str | None, project_id: str | None) -> bool:
    scope, identity = scope_identity(record)
    return scope == "user" or bool(identity) and (
        scope == "session" and identity == session_key
        or scope == "project" and identity == project_id
    )


def visibility_filter(session_key: str | None, project_id: str | None) -> tuple[str, list[str]]:
    """SQL equivalent of visible; originating-session metadata grants no access."""
    return (
        "(m.scope='user' OR (m.scope='session' AND m.session_key=?) "
        "OR (m.scope='project' AND m.project_id=?))",
        [session_key or "", project_id or ""],
    )
