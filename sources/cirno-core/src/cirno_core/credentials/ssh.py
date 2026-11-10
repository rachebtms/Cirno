"""SSH connection fields shared by the vault, Nodes and owner forms."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from cirno_core.credentials.ssh_session import SSHSessionSettings


class SSHConnection(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    host: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9.:%_-]*$")
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
    auth_method: Literal["key", "password"] = "key"
    password: str = Field(default="", repr=False)
    identity_file: str = ""
    host_key: str = ""

    def agent_metadata(self) -> dict:
        """Describe a usable connection without exposing its authentication or environment values."""
        result = self.model_dump(include={"id", "name", "host", "port", "username", "auth_method",
                                          "working_directory", "init_script"})
        result.update(has_password=bool(self.password), has_identity_file=bool(self.identity_file))
        if isinstance(self, SSHSessionSettings):
            result["environment_names"] = sorted(self.environment)
        return result


class SSHCredential(SSHConnection, SSHSessionSettings):
    node_enabled: bool = False

    @model_validator(mode="after")
    def authentication(self):
        if self.auth_method == "password" and not self.password:
            raise ValueError("A password is required for password authentication")
        if self.auth_method == "key":
            self.password = ""
        return self

    def public(self) -> dict:
        return {**self.model_dump(exclude={"password"}), "has_password": bool(self.password)}
