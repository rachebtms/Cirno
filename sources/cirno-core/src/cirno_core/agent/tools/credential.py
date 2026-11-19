"""List credential metadata and explicitly read Agent-visible secret values."""

import asyncio
import json
from pathlib import Path

from cirno_core.agent.tools.base import Tool, ToolResult, tool_parameters
from cirno_core.agent.tools.schema import (
    IntegerSchema,
    ObjectSchema,
    StringSchema,
    tool_parameters_schema,
)
from cirno_core.config.loader import get_config_path
from cirno_core.credentials.service import Credentials
from cirno_core.storage.instance import InstanceData
from cirno_core.utils.cancellation import shield_and_drain


@tool_parameters(
    tool_parameters_schema(
        action=StringSchema(
            "list metadata, read one visible credential, store or delete.",
            enum=("list", "read", "store", "delete"),
        ),
        id=StringSchema("Record ID for read, update or delete."),
        label=StringSchema("Human-readable label; never put a secret in the label."),
        kind=StringSchema("Value type.", enum=("password", "text", "identity", "token", "ssh")),
        username=StringSchema("Optional account username, encrypted with the secret."),
        value=StringSchema("Sensitive value to encrypt; only required for store."),
        ssh=ObjectSchema(properties={
            "host": StringSchema(), "port": IntegerSchema(minimum=1, maximum=65535),
            "username": StringSchema(), "auth_method": StringSchema(enum=("key", "password")),
            "password": StringSchema(), "identity_file": StringSchema(), "host_key": StringSchema(),
            "working_directory": StringSchema("Remote startup directory; ~ resolves on the SSH host."),
            "init_script": StringSchema("Remote Bash initialization script path."),
            "environment": ObjectSchema(additional_properties={"type": "string"}, description="Remote environment variables."),
        }, additional_properties=False, description="SSH connection to encrypt. Only the owner can enable it as an SSH Node."),
        required=["action"],
    )
)
class CredentialTool(Tool):
    def __init__(self, *, source_config_path: Path | None = None):
        source = source_config_path if source_config_path is not None else get_config_path()
        self.state_dir = Path(source).expanduser().resolve(strict=False).parent / "state"

    @classmethod
    def create(cls, ctx):
        return cls(source_config_path=ctx.source_config_path or ctx.instance_config_path)

    @property
    def name(self):
        return "credential"

    @property
    def description(self):
        return "Manage the owner's encrypted personal credentials. List returns metadata only; use credentials.read with a record ID to retrieve its secret value and account username, or its SSH connection fields. Only Agent-visible records can be listed, read or managed; Agent-created and updated records are visible. Read a secret only when needed for the user's task. Do not copy secrets into replies, memory, titles, reports or labels. SSH Node enrollment remains controlled by the owner. Values remain encrypted on disk."

    def approval_reason(self, params):
        if params.get("action") == "delete" or params.get("action") == "store" and params.get("id"):
            return "Delete or replace an encrypted personal credential"
        return None

    async def execute(self, action="list", id=None, label="", kind="text", value=None, username="", ssh=None):
        def run():
            vault = Credentials(data=InstanceData(self.state_dir), actor="agent")
            if action == "list":
                result = vault.list()
            elif action == "read":
                if not id:
                    return ToolResult.error("Choose a credential ID to read")
                result = vault.reveal(id)
            elif action == "store":
                result = vault.save(id=id, label=label, kind=kind, value=value, username=username, ssh=ssh)
            elif action == "delete":
                result = vault.delete(id)
            else:
                return ToolResult.error("Unknown credential operation")
            return ToolResult(json.dumps(result, ensure_ascii=False), sensitive=action == "read")
        try:
            return await shield_and_drain(asyncio.to_thread(run))
        except (ValueError, KeyError, OSError) as exc:
            return ToolResult.error(str(exc))
