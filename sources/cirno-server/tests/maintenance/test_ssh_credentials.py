"""Upgrade legacy Node records without breaking remote jobs or keeping plaintext."""
from pathlib import Path

import pytest
from cirno_core.credentials.service import Credentials
from cirno_core.nodes.service import Nodes
from cirno_core.storage.instance import InstanceData
from cirno_server.maintenance.migrations.ssh_credentials import migrate_ssh_credentials
from cirno_vault.vault import CredentialVault


def test_import_retries_after_ciphertext_commit_and_keeps_job_identity(tmp_path: Path, monkeypatch):
    data = InstanceData(tmp_path / 'state')
    node = data.save('nodes', {'name': 'Existing GPU', 'host': 'gpu.example', 'username': 'owner',
                              'auth_method': 'password', 'password': 'legacy-password'})
    data.save('node_jobs', {'node_id': node['id'], 'state': 'running'})
    save = CredentialVault.save
    def interrupted(self, **values):
        save(self, **values)
        raise OSError('interrupted after encrypted commit')
    with monkeypatch.context() as patch:
        patch.setattr(CredentialVault, 'save', interrupted)
        with pytest.raises(OSError, match='interrupted'):
            migrate_ssh_credentials(tmp_path)
    assert data.list('nodes')
    assert migrate_ssh_credentials(tmp_path)
    assert not migrate_ssh_credentials(tmp_path)
    current = Nodes(data, actor='agent').node(node['id'])
    assert current.password == 'legacy-password'
    assert data.list('node_jobs')[0]['node_id'] == current.id
    assert len(Credentials(data).list()['records']) == 1
    assert data.list('nodes') == []
    assert b'legacy-password' not in data.path.read_bytes()


def test_import_conflict_retains_the_original_and_does_not_replace_a_credential(tmp_path: Path):
    data = InstanceData(tmp_path / 'state')
    node = data.save('nodes', {'name': 'GPU', 'host': 'gpu.example', 'username': 'owner'})
    vault = CredentialVault(tmp_path / 'state' / 'credentials')
    vault.save(label='Personal', kind='text', value='private-text', create_id=node['id'])
    with pytest.raises(ValueError, match='already exists'):
        migrate_ssh_credentials(tmp_path)
    assert vault.reveal(node['id'])['value'] == 'private-text'
    assert data.list('nodes') == [node]
