"""Verified caches, package restoration and failed executable probes."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from cirno_setup import apt
from cirno_setup.artifacts import download
from cirno_setup.context import Context
from cirno_setup.policy import Policy


@pytest.fixture
def context(tmp_path):
    home = tmp_path / "home"
    (home / ".cirno").mkdir(parents=True)
    assets = tmp_path / "assets"
    assets.mkdir()
    return Context(home, assets, Policy())

def test_valid_download_cache_is_reused_and_corruption_is_replaced(context, monkeypatch):
    contents = b"verified dependency archive"
    expected = hashlib.sha256(contents).hexdigest()
    cached = context.root / "downloads" / expected
    cached.parent.mkdir(parents=True)
    cached.write_bytes(contents)
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        Path(arguments[arguments.index("--output") + 1]).write_bytes(contents)

    monkeypatch.setattr(context, "run", run)
    assert download(context, "https://example.invalid/tool", expected) == cached
    assert not calls
    cached.write_bytes(b"interrupted or corrupted download")
    assert download(context, "https://example.invalid/tool", expected).read_bytes() == contents
    assert len(calls) == 1


def test_apt_restore_only_installs_missing_packages_and_honors_version_pins(context, monkeypatch):
    state = context.root / "apt" / "packages.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps(["hello=2.0", "ed", "libdemo:arm64"]))
    monkeypatch.setattr(apt, "installed_packages", lambda: {"ed": "1", "libdemo:arm64": "1"})
    calls = []
    monkeypatch.setattr(context, "run", lambda argv, **kwargs: calls.append(argv))
    monkeypatch.setattr(apt, "record", lambda _, **kwargs: None)
    apt.restore(context)
    assert calls[0] == ["/usr/bin/apt-get", "update"]
    assert calls[1][-2:] == ["--", "hello=2.0"]
    assert not any("ed" in args for args in calls)


def test_apt_cache_uses_the_same_instance_and_preserves_other_apt_hooks(
    context, monkeypatch, tmp_path
):
    hooks = tmp_path / "apt-config"
    hooks.mkdir()
    (hooks / "docker-clean").write_text("delete archives")
    (hooks / "custom-hook").write_text("keep this hook")
    monkeypatch.setattr(apt, "APT_CONFIG_DIR", hooks)
    apt.configure_cache(context)
    assert not (hooks / "docker-clean").exists()
    assert (hooks / "custom-hook").read_text() == "keep this hook"
    assert str(context.root / "apt" / "archives") in (hooks / "99cirno-cache").read_text()


def test_apt_record_retains_only_packages_added_to_the_image(context, monkeypatch):
    (context.assets / "base-apt-packages.json").write_text('["git", "curl"]')
    monkeypatch.setattr(apt, "manual_packages", lambda: {"git", "curl", "hello"})
    monkeypatch.setattr(apt.os, "chown", lambda *args, **kwargs: None)
    apt.record(context)
    assert apt.recorded_packages(context) == ["hello"]
    monkeypatch.setattr(apt, "manual_packages", lambda: {"git", "curl"})
    apt.record(context)
    assert apt.recorded_packages(context) == []


def test_broken_managed_executable_is_a_failed_probe(context, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("Exec format error")

    monkeypatch.setattr(subprocess, "run", broken)
    assert not context.probe(["/broken/tool", "--version"])



def test_setup_managed_apt_packages_are_not_confused_with_user_additions(context, monkeypatch):
    directory = context.root / "apt"
    directory.mkdir(parents=True)
    (context.assets / "base-apt-packages.json").write_text('["git"]')
    (directory / "managed.json").write_text('["libreoffice-writer"]')
    (directory / "observed.json").write_text('["git"]')
    monkeypatch.setattr(apt.os, "chown", lambda *args, **kwargs: None)
    monkeypatch.setattr(apt, "manual_packages", lambda: {"git", "libreoffice-writer"})
    monkeypatch.setenv("CIRNO_APT_MANAGED", "1")
    apt.record(context)
    assert apt.recorded_packages(context) == []
    monkeypatch.delenv("CIRNO_APT_MANAGED")
    monkeypatch.setattr(apt, "manual_packages", lambda: {"git", "libreoffice-writer", "hello"})
    apt.record(context)
    assert apt.recorded_packages(context) == ["hello"]
    # A new container can omit Office; installing it manually afterwards records
    # a real user addition even if an old preset once managed the package.
    monkeypatch.setattr(apt, "manual_packages", lambda: {"git"})
    apt.observe(context)
    monkeypatch.setattr(apt, "manual_packages", lambda: {"git", "libreoffice-writer"})
    apt.record(context)
    assert apt.recorded_packages(context) == ["libreoffice-writer"]


def test_flat_official_archive_retains_notices_and_normalizes_executable(context, tmp_path, monkeypatch):
    import io
    import tarfile

    from cirno_setup import artifacts

    archive = tmp_path / "xurl.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        for name, contents in {"xurl": b"binary fixture", "LICENSE": b"license fixture"}.items():
            member = tarfile.TarInfo(name)
            member.size = len(contents)
            output.addfile(member, io.BytesIO(contents))
    (context.assets / "artifacts.json").write_text(json.dumps({
        "xurl": {"layout": "flat", context.architecture: {"url": "https://example.invalid/xurl", "sha256": "fixture"}},
    }))
    monkeypatch.setattr(artifacts, "download", lambda *args: archive)
    artifacts.install_archive(context, "xurl")
    assert (context.managed / "xurl/bin/xurl").read_bytes() == b"binary fixture"
    assert (context.managed / "xurl/LICENSE").read_bytes() == b"license fixture"


@pytest.mark.parametrize("output,ready", [("xurl version 1.3.4\n", True), ("xurl version v1.3.4\n", True), ("xurl version 1.3.3\n", False)])
def test_official_xurl_release_version_probe(context, monkeypatch, output, ready):
    from cirno_setup.backends.archive import verify
    from cirno_setup.recipe import Recipe

    (context.assets / "artifacts.json").write_text('{"xurl":{"version":"1.3.4"}}')
    command = context.managed / "xurl/bin/xurl"
    command.parent.mkdir(parents=True)
    command.touch()
    monkeypatch.setattr(context, "inspect", lambda _: subprocess.CompletedProcess([], 0, output, ""))
    assert verify(context, Recipe(provider="archive", packages=("xurl",))).ready is ready


def test_ytdlp_uses_standard_configuration_and_preserves_user_options(context, monkeypatch):
    from cirno_setup.recipes.pip.yt_dlp import recipe

    monkeypatch.setattr("cirno_setup.backends.pip.install", lambda *args: None)
    recipe.install(context)
    config = context.home / ".config/yt-dlp/config"
    assert config.read_text() == "--js-runtimes node\n"
    config.write_text("--format bestaudio\n")
    recipe.install(context)
    assert config.read_text() == "--format bestaudio\n"


def test_nvm_installs_into_standard_directory_without_removing_node_versions(context, tmp_path, monkeypatch):
    import io
    import tarfile

    from cirno_setup.backends import nvm
    from cirno_setup.recipe import Recipe

    archive = tmp_path / "nvm.tar.gz"
    content = b"official nvm script fixture"
    with tarfile.open(archive, "w:gz") as output:
        member = tarfile.TarInfo("nvm-release/nvm.sh")
        member.size = len(content)
        output.addfile(member, io.BytesIO(content))
    (context.assets / "artifacts.json").write_text(json.dumps({
        "nvm": {context.architecture: {"url": "https://example.invalid/nvm", "sha256": "fixture"}},
    }))
    version = context.root / "nvm/versions/node/existing/bin/node"
    version.parent.mkdir(parents=True)
    version.write_text("user Node version")
    monkeypatch.setattr(nvm, "download", lambda *args: archive)
    nvm.install(context, Recipe())
    assert (context.root / "nvm/nvm.sh").read_bytes() == content
    assert version.read_text() == "user Node version"
