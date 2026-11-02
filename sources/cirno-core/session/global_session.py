"""Create the personal Cirno conversation independently of transports."""

from cirno_core.session.keys import CIRNO_SESSION_KEY

GLOBAL_SESSION_KEY = CIRNO_SESSION_KEY


async def ensure_global_session(sessions):
    session = await sessions.state.get(GLOBAL_SESSION_KEY)
    if not session.metadata.get("is_global") or session.metadata.get("title") != "Cirno" or session.metadata.get("session_handle") != "cirno":
        await sessions.state.update_metadata(GLOBAL_SESSION_KEY, {"is_global": True, "title": "Cirno", "webui": True, "session_handle": "cirno"})
    return GLOBAL_SESSION_KEY
