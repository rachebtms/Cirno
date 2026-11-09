"""Manage encrypted values without recalling them into model context."""

import asyncio
import json

from cirno_core.agent.tools.base import Tool, ToolResult, tool_parameters
from cirno_core.agent.tools.schema import (
    IntegerSchema,
    ObjectSchema,
    StringSchema,
    tool_parameters_schema,
)
from cirno_core.credentials.service import Credentials


@tool_parameters(
    tool_parameters_schema(
        action=StringSchema(
            "list, store or delete. Secret values cannot be read by this tool.",
            enum=("list", "store", "delete"),
        ),
        id=StringSchema("Record ID for update/delete."),
        label=StringSchema("Human-readable label; never put a secret in the label."),
        kind=StringSchema("Value type.", enum=("password", "text", "identity", "token", "ssh")),
        username=StringSchema("Optional account username, encrypted with the secret."),
        value=StringSchema("Sensitive value to encrypt; only required for store."),
        ssh=ObjectSchema(properties={
            "host": StringSchema(), "port": IntegerSchema(minimum=1, maximum=65535),
            "username": StringSchema(), "auth_method": StringSchema(enum=("key", "password")),
            "password": StringSchema(), "identity_file": StringSchema(), "host_key": StringSchema(),
            "init_script": StringSchema("Remote Bash initialization script path."),
            "environment": ObjectSchema(additional_properties={"type": "string"}, description="Remote environment variables."),
        }, additional_properties=False, description="SSH connection to encrypt. Only the owner can enable it as an SSH Node."),
        required=["action"],
    )
)
class CredentialTool(Tool):
    @property
    def name(self):
        return "credential"

    @property
    def description(self):
        return "Manage the owner's encrypted personal credentials: list metadata, store/update a known secret or long text, or delete an explicitly identified record. Only Agent-visible records can be listed or managed; Agent-created and updated records are visible. Values are encrypted on disk and never returned to model context. Do not put secrets in memory, files, titles, reports or labels. SSH records stay unavailable to remote tools until the owner enables them as SSH Nodes. Prefer owner entry through the Credentials tab. Previously pasted chat secrets remain in that chat."

    def approval_reason(self, params):
        if params.get("action") == "delete" or params.get("action") == "store" and params.get("id"):
            return "Delete or replace an encrypted personal credential"
        return None

    async def execute(self, action="list", id=None, label="", kind="text", value=None, username="", ssh=None):
        vault = Credentials(actor="agent")
        try:
            if action == "list":
                result = await asyncio.to_thread(vault.list)
            elif action == "store":
                result = await asyncio.to_thread(
                    vault.save, id=id, label=label, kind=kind, value=value, username=username, ssh=ssh
                )
            elif action == "delete":
                result = await asyncio.to_thread(vault.delete, id)
            else:
                return ToolResult.error("Unknown credential operation")
            return json.dumps(result, ensure_ascii=False)
        except (ValueError, KeyError) as exc:
            return ToolResult.error(str(exc))
