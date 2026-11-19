"""Failed first access and missing keys must not strand or mix vault records."""

import os
import sqlite3

import pytest
from cirno_vault.vault import CredentialVault
from cryptography.fernet import Fernet


@pytest.mark.parametrize("failure", ["generation", "file-sync"])
def test_failed_key_initialization_leaves_no_live_partial_key_and_can_retry(tmp_path, monkeypatch, failure):
    generate, sync = Fernet.generate_key, os.fsync

    def fail(*_args):
        raise OSError("Fixture key initialization failed")

    if failure == "generation":
        monkeypatch.setattr(Fernet, "generate_key", fail)
    else:
        monkeypatch.setattr("cirno_vault.vault.os.fsync", fail)
    vault = CredentialVault(tmp_path)
    with pytest.raises(OSError, match="initialization failed"):
        vault.list()
    assert not (tmp_path / "vault.key").exists()
    monkeypatch.setattr(Fernet, "generate_key", generate)
    monkeypatch.setattr("cirno_vault.vault.os.fsync", sync)
    assert vault.list() == {"records": []}
    Fernet((tmp_path / "vault.key").read_bytes())


def test_missing_key_does_not_create_a_second_key_for_an_existing_vault(tmp_path):
    vault = CredentialVault(tmp_path)
    row = vault.save(label="Existing fixture", value="existing-fixture")
    key, backup = tmp_path / "vault.key", tmp_path / "original-key"
    key.rename(backup)
    database = (tmp_path / "vault.sqlite3").read_bytes()
    try:
        with pytest.raises(ValueError, match="key.*missing|missing.*key"):
            vault.save(label="New fixture", value="new-fixture")
        assert not key.exists()
        assert (tmp_path / "vault.sqlite3").read_bytes() == database
    finally:
        backup.replace(key)
    assert vault.reveal(row["id"]) == {"value": "existing-fixture"}
    assert vault.list()["records"] == [row]


def test_schema_failure_closes_the_opened_database(tmp_path, monkeypatch):
    (tmp_path / "vault.key").write_bytes(Fernet.generate_key())
    (tmp_path / "vault.sqlite3").write_bytes(b"")
    closed = []

    class Connection:
        def execute(self, *_args):
            raise sqlite3.OperationalError("Fixture schema locked")

        def close(self):
            closed.append(True)

    monkeypatch.setattr("cirno_vault.vault.sqlite3.connect", lambda *_args: Connection())
    with pytest.raises(sqlite3.OperationalError, match="schema locked"):
        CredentialVault(tmp_path).list()
    assert closed == [True]
