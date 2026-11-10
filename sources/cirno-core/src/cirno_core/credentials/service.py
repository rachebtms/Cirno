"""One credential owner for browser forms, Agent metadata and SSH enrollment."""
from __future__ import annotations

from cirno_vault.vault import CredentialVault
from filelock import FileLock

from cirno_core.credentials.ssh import SSHCredential
from cirno_core.storage.instance import InstanceData


class Credentials:
    def __init__(self, data: InstanceData | None = None, *, actor: str = "owner"):
        self.actor = actor
        self.data = data or InstanceData()
        self.vault = CredentialVault(self.data.state_dir / "credentials")

    def ssh_records(self) -> list[tuple[dict, SSHCredential]]:
        return [(record, SSHCredential.model_validate_json(record["value"]))
                for record in self.vault.decrypted_records("ssh") if self.actor == "owner" or record["agent_visible"]]

    def _lease(self):
        self.vault.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        return FileLock(self.vault.directory / "records.lock", timeout=10, mode=0o600)

    def list(self) -> dict:
        with self._lease():
            enabled = {record["id"]: ssh.node_enabled for record, ssh in self.ssh_records()}
            return {"records": [{**record, **({"node_enabled": enabled[record["id"]]} if record["kind"] == "ssh" else {})}
                                for record in self.vault.list()["records"] if self.actor == "owner" or record["agent_visible"]]}

    def _check_access(self, record: dict) -> dict:
        if self.actor == "agent" and not record["agent_visible"]:
            raise ValueError("Credential is not available to the Agent")
        return record

    def _accessible(self, identifier: str) -> dict:
        return self._check_access(self.vault.metadata(identifier))

    def connection(self, identifier: str) -> tuple[dict, SSHCredential]:
        record = self._check_access(self.vault.read_record(identifier))
        if record["kind"] != "ssh":
            raise ValueError("Choose an SSH credential")
        return record, SSHCredential.model_validate_json(record["value"])

    def ssh(self, identifier: str) -> SSHCredential:
        return self.connection(identifier)[1]

    def describe(self, identifier: str) -> dict:
        record = self._check_access(self.vault.read_record(identifier))
        metadata = {key: record[key] for key in ("id", "label", "kind", "agent_visible")}
        if record["kind"] == "ssh":
            ssh = SSHCredential.model_validate_json(record["value"])
            metadata["ssh"] = ssh.agent_metadata() if self.actor == "agent" else ssh.public()
        return metadata

    def reveal(self, identifier: str) -> dict:
        if self.actor != "owner":
            raise ValueError("Only the owner can reveal credential values")
        record = self._check_access(self.vault.read_record(identifier))
        if record["kind"] == "ssh":
            return {"ssh": SSHCredential.model_validate_json(record["value"]).model_dump()}
        return {key: record[key] for key in ("value", "username") if key in record}

    def _require_no_jobs(self, identifier: str) -> None:
        if any(job["node_id"] == identifier and job.get("state") in {"running", "submitting", "submission_unknown"}
               for job in self.data.list("node_jobs")):
            raise ValueError("Stop or resolve this Node’s jobs before changing its connection or removing access")

    def save(self, *, label: str, kind: str = "text", id: str | None = None,
             value: str | None = None, username: str = "", ssh: dict | None = None,
             node_enabled: bool | None = None, working_directory: str | None = None, agent_visible: bool | None = None) -> dict:
        with self._lease():
            return self._save(label=label, kind=kind, id=id, value=value, username=username, ssh=ssh,
                              node_enabled=node_enabled, working_directory=working_directory, agent_visible=agent_visible)

    def _save(self, *, label, kind, id=None, value=None, username="", ssh=None, node_enabled=None, working_directory=None, agent_visible=None):
        metadata = self._accessible(id) if id else None
        previous = self.ssh(id) if metadata and metadata["kind"] == "ssh" else None
        visibility = True if self.actor == "agent" else agent_visible if agent_visible is not None else bool(metadata and metadata["agent_visible"])
        if kind == "ssh":
            fields = {**(previous.model_dump() if previous else {}), **dict(ssh or {})}
            # A blank password in an owner edit retains the encrypted value.
            if previous and not fields.get("password"):
                fields["password"] = previous.password
            fields["node_enabled"] = node_enabled if node_enabled is not None else bool(previous and previous.node_enabled)
            if working_directory is not None:
                fields["working_directory"] = working_directory
            current = SSHCredential.model_validate(fields)
            if previous and previous != current:
                self._require_no_jobs(id)
            value, username = current.model_dump_json(), ""
        else:
            if previous:
                self._require_no_jobs(id)
            if metadata and metadata["kind"] == kind and not value:
                stored = self.vault.reveal(id)
                value = stored["value"]
                username = username or stored.get("username", "")
        return self.vault.save(id=id, label=label, kind=kind, value=value, username=username, agent_visible=visibility)

    def enroll(self, identifier: str, *, enabled: bool, working_directory: str | None = None,
               init_script: str | None = None, environment: dict[str, str] | None = None) -> dict:
        if self.actor != "owner":
            raise ValueError("Only the owner can change SSH Node enrollment")
        with self._lease():
            record, connection = self.connection(identifier)
            fields = connection.model_dump(exclude={"node_enabled", "working_directory"})
            fields.update({key: value for key, value in {"init_script": init_script, "environment": environment}.items() if value is not None})
            return self._save(id=identifier, label=record["label"], kind="ssh", ssh=fields,
                              node_enabled=enabled, working_directory=working_directory)

    def delete(self, identifier: str) -> dict:
        with self._lease():
            self._accessible(identifier)
            self._require_no_jobs(identifier)
            return self.vault.delete(identifier)
