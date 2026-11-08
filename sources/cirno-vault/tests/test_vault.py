"""Encrypted records retain values across reopen and concurrent initialization."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from cirno_vault.vault import CredentialVault


def test_vault_encrypts_long_values_and_survives_restart(tmp_path):
    secret = "personal-secret-" + "文本" * 1000
    vault = CredentialVault(tmp_path)
    row = vault.save(label="Personal record", value=secret, kind="identity")
    assert "value" not in vault.list()["records"][0]
    assert CredentialVault(tmp_path).reveal(row["id"]) == {"value": secret}
    for file in tmp_path.iterdir():
        assert secret.encode() not in file.read_bytes()
    vault.save(id=row["id"], label="Updated", value="new-secret")
    assert len(vault.list()["records"]) == 1
    assert vault.reveal(row["id"]) == {"value": "new-secret"}
    vault.delete(row["id"])
    with pytest.raises(KeyError):
        vault.reveal(row["id"])
    with pytest.raises(KeyError):
        vault.save(id=row["id"], label="No resurrection", value="secret")



def test_concurrent_first_access_uses_one_encryption_key(tmp_path):
    def save(index):
        return CredentialVault(tmp_path).save(label=str(index), value=str(index))

    with ThreadPoolExecutor(max_workers=4) as workers:
        records = list(workers.map(save, range(8)))
    vault = CredentialVault(tmp_path)
    assert all(vault.reveal(row["id"])["value"] == row["label"] for row in records)



def test_account_usernames_are_encrypted_and_not_listed(tmp_path):
    vault = CredentialVault(tmp_path)
    row = vault.save(
        label="Account",
        kind="password",
        username="private-user@example.org",
        value="private-password",
    )
    assert vault.reveal(row["id"]) == {
        "username": "private-user@example.org",
        "value": "private-password",
    }
    assert vault.list()["records"] == [row]
    for file in tmp_path.iterdir():
        assert b"private-user@example.org" not in file.read_bytes()
        assert b"private-password" not in file.read_bytes()



def _write_in_process(directory, started, release, results, slow):
    from cryptography.fernet import Fernet

    if slow:
        generate = Fernet.generate_key

        def delayed_key():
            started.set()
            if not release.wait(10):
                raise TimeoutError("test did not release key writer")
            return generate()

        Fernet.generate_key = delayed_key
    else:
        started.set()
    try:
        record = CredentialVault(directory).save(label="writer-" + str(slow), value="secret")
        results.put((record["id"], None))
    except Exception as error:
        results.put((None, str(error)))


def test_other_process_waits_for_the_first_complete_encryption_key(tmp_path):
    import multiprocessing
    import time

    context = multiprocessing.get_context("spawn")
    key_started, second_started, release = (context.Event() for _ in range(3))
    results = context.Queue()
    first = context.Process(target=_write_in_process, args=(tmp_path, key_started, release, results, True))
    second = context.Process(target=_write_in_process, args=(tmp_path, second_started, release, results, False))
    first.start()
    try:
        assert key_started.wait(10)
        second.start()
        assert second_started.wait(10)
        # The first key file exists but its contents have not been written yet.
        time.sleep(0.1)
    finally:
        release.set()
        for process in (first, second):
            if process.pid is not None:
                process.join(timeout=10)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=5)
    assert first.exitcode == second.exitcode == 0
    outcomes = [results.get(timeout=2), results.get(timeout=2)]
    results.close()
    assert all(error is None for _, error in outcomes), outcomes
    vault = CredentialVault(tmp_path)
    assert len(vault.list()["records"]) == 2
    assert all(vault.reveal(identifier)["value"] == "secret" for identifier, _ in outcomes)


def test_existing_four_column_vault_migrates_without_changing_ciphertext(tmp_path):
    import json
    import sqlite3
    from cryptography.fernet import Fernet
    tmp_path.mkdir(exist_ok=True)
    key = Fernet.generate_key()
    (tmp_path / 'vault.key').write_bytes(key)
    encrypted = Fernet(key).encrypt(json.dumps({'value': 'existing-secret'}).encode())
    with sqlite3.connect(tmp_path / 'vault.sqlite3') as db:
        db.execute('CREATE TABLE records (id TEXT PRIMARY KEY,label TEXT NOT NULL,kind TEXT NOT NULL,encrypted BLOB NOT NULL)')
        db.execute('INSERT INTO records VALUES (?,?,?,?)', ('existing', 'Personal', 'password', encrypted))
    vault = CredentialVault(tmp_path)
    assert vault.list()['records'] == [{'id': 'existing', 'label': 'Personal', 'kind': 'password', 'agent_visible': False}]
    assert vault.reveal('existing')['value'] == 'existing-secret'
    with sqlite3.connect(tmp_path / 'vault.sqlite3') as db:
        assert db.execute('SELECT encrypted FROM records').fetchone()[0] == encrypted
