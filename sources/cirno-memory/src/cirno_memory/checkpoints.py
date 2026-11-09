"""Choose task checkpoints by conversation and visibility scope."""

import hashlib
import json

from cirno_memory.scopes import scope_identity


def checkpoint_id(repo, session_key: str, project_id: str | None) -> str:
    scoped = "task-" + hashlib.sha256(json.dumps([session_key, project_id]).encode()).hexdigest()[:32]
    legacy = "task-" + hashlib.sha256(session_key.encode()).hexdigest()[:32]
    scope = ("project", project_id) if project_id else ("session", session_key)
    with repo.connect() as db:
        for identity in (scoped, legacy):
            row = db.execute("SELECT body FROM memories WHERE id=?", (identity,)).fetchone()
            if row and scope_identity(json.loads(row[0])) == scope:
                return identity
    return scoped
