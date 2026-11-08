"""Authenticated access to owner presentation preferences."""

import asyncio

from cirno_core.profile.preferences import PreferenceConflictError
from cirno_server.webui.http_utils import (
    http_error as _http_error,
)
from cirno_server.webui.http_utils import (
    http_json_response as _http_json_response,
)

from .shared import (
    _NO_STORE_HEADERS,
    _WEBUI_MUTATION_REQUEST_ATTR,
    _mutation_payload,
)


async def preferences_response(server, request):
    if not getattr(request, _WEBUI_MUTATION_REQUEST_ATTR, False):
        return _http_error(405, "Preference changes require an authenticated connection")
    payload = _mutation_payload(request) or {}
    try:
        if payload.get("operation") == "read":
            body = await asyncio.to_thread(server.preferences.read)
        else:
            body = await asyncio.to_thread(
                server.preferences.update,
                payload.get("patch", {}),
                payload.get("expected_revision"),
            )
    except PreferenceConflictError as error:
        return _http_error(409, str(error))
    except ValueError as error:
        return _http_error(400, str(error))
    return _http_json_response(body, extra_headers=_NO_STORE_HEADERS)
