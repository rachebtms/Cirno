"""Notice payload accepted by the durable Inbox."""

from typing import Any, NotRequired, TypedDict


class NoticeDraft(TypedDict):
    identifier: str
    category: str
    kind: str
    session_key: str
    status: NotRequired[str]
    body: NotRequired[str]
    data: NotRequired[dict[str, Any]]
