"""Instance-owned settings for remote job monitoring and local record retention."""

from pydantic import BaseModel, ConfigDict, Field

from cirno_core.storage.instance import InstanceData

ACTIVE_JOB_STATES = frozenset({"running", "submitting", "submission_unknown", "unknown"})
TERMINAL_JOB_STATES = frozenset({"completed", "failed", "stopped"})


class NodeJobPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    poll_interval_seconds: int = Field(default=60, ge=0, le=9007199254740991, strict=True)
    retention_days: int = Field(default=30, ge=0, le=9007199254740991, strict=True)


def read_policy(data: InstanceData) -> NodeJobPolicy:
    try:
        record = data.get("node_settings", "jobs")
    except KeyError:
        return NodeJobPolicy()
    return NodeJobPolicy.model_validate({key: value for key, value in record.items() if key != "id"})


def save_policy(data: InstanceData, values: dict) -> NodeJobPolicy:
    def update(record):
        current = {key: value for key, value in record.items() if key != "id"}
        return NodeJobPolicy.model_validate({**current, **values}).model_dump()
    saved = data.update("node_settings", "jobs", update, initial=NodeJobPolicy().model_dump())
    return NodeJobPolicy.model_validate({key: value for key, value in saved.items() if key != "id"})
