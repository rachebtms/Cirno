"""Move existing Node authentication into the encrypted vault, keeping Node IDs."""
from __future__ import annotations

from pathlib import Path

from cirno_core.credentials.ssh import SSHCredential
from cirno_core.nodes.service import Node
from cirno_core.storage.instance import InstanceData
from cirno_vault.vault import CredentialVault


def migrate_ssh_credentials(instance: Path) -> bool:
    state = instance / "state"
    if not (state / "instance.sqlite3").exists():
        return False
    data = InstanceData(state)
    records = data.list("nodes")
    if not records:
        return False
    from cirno_server.maintenance.startup import require_stopped_instance
    require_stopped_instance(instance / "config.json")
    vault = CredentialVault(state / "credentials")
    existing = {record["id"]: record for record in vault.decrypted_records("ssh")}
    for record in records:
        node = Node.model_validate(record)
        credential = SSHCredential(**node.model_dump(exclude={"id", "name"}), node_enabled=True)
        encrypted = existing.get(node.id)
        if encrypted is not None:
            if encrypted["label"] != node.name or SSHCredential.model_validate_json(encrypted["value"]) != credential:
                raise ValueError(f"SSH credential migration conflict for Node {node.id}")
        else:
            vault.save(label=node.name, kind="ssh", value=credential.model_dump_json(), create_id=node.id, agent_visible=True)
        # Committed ciphertext precedes retiring the old row. A failed migration
        # retries the same ID; SQLite erases deleted plaintext, including free pages.
        with data.connect() as connection:
            connection.execute("PRAGMA secure_delete=ON")
            connection.execute("DELETE FROM records WHERE kind='nodes' AND id=?", (node.id,))
    with data.connect() as connection:
        connection.execute("VACUUM")
    return True
