"""Real vault and Node policy, including revocation and secret-safe failures."""
import json
import os

import pytest
from cirno_core.agent.tools.credential import CredentialTool
from cirno_core.credentials.service import Credentials
from cirno_core.nodes.service import Nodes
from cirno_core.storage.instance import InstanceData


@pytest.fixture
def credentials(tmp_path):
    return Credentials(InstanceData(tmp_path / "state"))


def test_owner_default_hidden_agent_mutations_visible_and_hidden_ids_rejected(credentials):
    private = credentials.save(label="Private", value="personal")
    agent = Credentials(credentials.data, actor="agent")
    assert agent.list() == {"records": []}
    for operation in (lambda: agent.save(id=private['id'], label="Changed", value="replacement"),
                      lambda: agent.delete(private['id'])):
        with pytest.raises(ValueError, match="not available"):
            operation()
    credentials.save(id=private['id'], label="Shared", agent_visible=True)
    assert credentials.reveal(private['id'])['value'] == 'personal'
    assert agent.list()['records'][0]['id'] == private['id']
    credentials.save(id=private['id'], label="Private again", agent_visible=False)
    public = agent.save(label="Agent record", value="known-secret")
    assert public['agent_visible'] is True
    changed = agent.save(id=public['id'], label="Updated", value="new-secret", agent_visible=False)
    assert changed['agent_visible'] is True
    assert "secret" not in json.dumps(agent.list())
    credentials.save(id=public['id'], label="Hidden again", value="new-secret", agent_visible=False)
    assert agent.list() == {"records": []}


def test_ssh_is_encrypted_and_two_independent_opt_ins_control_execution(credentials):
    ssh = {"host": "gpu.example", "username": "researcher", "auth_method": "password", "password": "ssh-private-secret"}
    record = credentials.save(label="GPU", kind="ssh", ssh=ssh)
    nodes = Nodes(credentials.data)
    agent_nodes = Nodes(credentials.data, actor="agent")
    assert nodes.list_nodes() == []
    with pytest.raises(ValueError, match="not enabled"):
        nodes.node(record['id'])
    nodes.save_node({"credential_id": record['id'], "working_directory": "/research"})
    assert nodes.node(record['id']).password == "ssh-private-secret"
    assert agent_nodes.list_nodes() == []
    assert nodes.list_nodes()[0]["agent_visible"] is False
    with pytest.raises(ValueError, match="not available"):
        agent_nodes.node(record['id'])
    credentials.save(id=record['id'], label="GPU", kind="ssh", ssh={**ssh, "password": ""}, agent_visible=True)
    assert agent_nodes.node(record['id']).working_directory == "/research"
    assert "ssh-private-secret" not in json.dumps(nodes.list_nodes())
    assert "password" not in credentials.describe(record['id'])['ssh']
    assert credentials.reveal(record['id'])['ssh']['password'] == "ssh-private-secret"
    for path in credentials.data.state_dir.rglob('*'):
        if path.is_file():
            assert b"ssh-private-secret" not in path.read_bytes()
    nodes.remove_node(record['id'])
    assert nodes.list_nodes() == []
    assert credentials.vault.metadata(record['id'])['kind'] == 'ssh'


def test_running_job_preserves_connection_and_credential_until_resolved(credentials):
    record = credentials.save(label="GPU", kind="ssh", ssh={"host": "gpu.example", "username": "owner"}, node_enabled=True)
    job = credentials.data.save('node_jobs', {"node_id": record['id'], "state": "submission_unknown"})
    for operation in (lambda: Nodes(credentials.data).remove_node(record['id']), lambda: credentials.delete(record['id']),
                      lambda: credentials.save(id=record['id'], label="GPU", kind="ssh", ssh={"host": "other.example", "username": "owner"})):
        with pytest.raises(ValueError, match="Stop or resolve"):
            operation()
    credentials.data.save('node_jobs', {**job, "state": "completed"})
    credentials.delete(record['id'])


async def test_agent_can_store_ssh_but_cannot_enroll_it(monkeypatch, credentials):
    monkeypatch.setattr('cirno_core.agent.tools.credential.Credentials', lambda **kwargs: Credentials(credentials.data, **kwargs))
    result = await CredentialTool().execute(action='store', label='Agent SSH', kind='ssh', ssh={"host": "host.example", "username": "owner", "node_enabled": True})
    identifier = json.loads(result)['id']
    assert credentials.vault.metadata(identifier)['agent_visible']
    assert not credentials.ssh(identifier).node_enabled
    assert Nodes(credentials.data, actor='agent').list_nodes() == []


def test_invalid_ssh_does_not_echo_the_secret(credentials):
    with pytest.raises(ValueError) as error:
        credentials.save(label='Invalid', kind='ssh', ssh={"host": "-invalid", "username": "owner", "password": "must-not-leak"})
    assert 'must-not-leak' not in str(error.value)


async def test_ipv6_transfers_and_auth_environment_use_the_saved_connection(credentials, monkeypatch):
    from unittest.mock import AsyncMock
    record = credentials.save(label='IPv6', kind='ssh', ssh={'host': '2001:db8::1', 'username': 'worker', 'port': 2222}, node_enabled=True)
    nodes = Nodes(credentials.data)
    run = AsyncMock(return_value='')
    monkeypatch.setattr(nodes, '_run', run)
    await nodes.transfer(record['id'], '/tmp/local', '/research/result')
    args = run.call_args.args[0]
    assert args[-1] == 'worker@[2001:db8::1]:/research/result'
    assert '-P' in args and '2222' in args


@pytest.mark.skipif(os.name != "posix", reason="OpenSSH askpass uses a POSIX shell helper")
def test_password_helpers_share_an_executable_without_sharing_values(credentials):
    from concurrent.futures import ThreadPoolExecutor
    import subprocess
    nodes = Nodes(credentials.data)
    with ThreadPoolExecutor(max_workers=8) as workers:
        environments = list(workers.map(nodes.environment, [f'password-{i}' for i in range(16)]))
    for index, environment in enumerate(environments):
        result = subprocess.run([environment['SSH_ASKPASS']], env=environment, capture_output=True, check=True, text=True)
        assert result.stdout == f'password-{index}\n'
    helper = credentials.data.state_dir / 'nodes/askpass'
    assert helper.stat().st_mode & 0o777 == 0o700
    assert 'password-' not in helper.read_text()
    before = helper.stat().st_mtime_ns
    nodes.environment("another-password")
    assert helper.stat().st_mtime_ns == before
