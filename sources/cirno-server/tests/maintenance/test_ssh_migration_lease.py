"""SSH credential migration participates in the instance migration lease."""

from contextlib import contextmanager

import pytest
from cirno_core.storage.instance import InstanceData
from cirno_server.maintenance.migrations.ssh_credentials import migrate_ssh_credentials
from filelock import FileLock, Timeout


def test_ssh_migration_holds_the_shared_lease_during_storage_access(tmp_path, monkeypatch):
    data = InstanceData(tmp_path / "state")
    data.save("nodes", {"name": "Fixture", "host": "fixture.invalid", "username": "owner", "auth_method": "password", "password": "fixture-secret"})
    directory = tmp_path / "state/migrations"
    directory.mkdir()
    connect = InstanceData.connect
    checked = []

    @contextmanager
    def require_lease(self):
        probe = FileLock(str(directory / ".lock"))
        with pytest.raises(Timeout):
            with probe.acquire(timeout=0):
                pass
        checked.append(True)
        with connect(self) as db:
            yield db

    with monkeypatch.context() as patch:
        patch.setattr(InstanceData, "connect", require_lease)
        assert migrate_ssh_credentials(tmp_path)
    assert len(checked) >= 3  # Covers initial read, row retirement and cleanup.
    assert data.list("nodes") == []
