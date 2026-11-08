from __future__ import annotations

import os
from contextlib import nullcontext
from pathlib import Path

import pytest
from cirno_server.webui.build import (
    ensure_webui_bundle,
    inspect_webui_bundle,
    pick_webui_build_runner,
)


@pytest.fixture(autouse=True)
def isolate_build_configuration(monkeypatch):
    monkeypatch.delenv("CIRNO_SKIP_WEBUI_BUILD", raising=False)


_MTIME_BASE_NS = 1_700_000_000_000_000_000
_MTIME_STEP_NS = 5_000_000_000


@pytest.mark.parametrize("checkout", [True, False])
def test_channel_serves_the_build_resolver_bundle(tmp_path, monkeypatch, checkout):
    from cirno_server.channels.webui_binding import _default_webui_dist

    package = tmp_path / "sources/cirno-server/src/cirno_server"
    package.mkdir(parents=True)
    if checkout:
        frontend = tmp_path / "sources" / "cirno-web"
        frontend.mkdir()
        (frontend / "package.json").write_text("{}")
        bundle = tmp_path / "build" / "webui"
    else:
        bundle = package / "web" / "dist"
    monkeypatch.setattr("cirno_server.webui.build.default_package_root", lambda: package)
    assert _default_webui_dist() is None
    bundle.mkdir(parents=True)
    (bundle / "index.html").write_text("<html>Cirno setup</html>")
    assert _default_webui_dist() == bundle


def _touch(path: Path, *, mtime_ns: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(path.name, encoding="utf-8")
    if mtime_ns < 1_000_000_000_000_000:
        mtime_ns = _MTIME_BASE_NS + mtime_ns * _MTIME_STEP_NS
    os.utime(path, ns=(mtime_ns, mtime_ns))


def test_inspect_webui_bundle_ignores_packaged_install_without_source(tmp_path: Path) -> None:
    source = tmp_path / "site-packages" / "webui"
    dist = tmp_path / "site-packages" / "cirno" / "web" / "dist"
    _touch(dist / "index.html", mtime_ns=20)

    status = inspect_webui_bundle(source_dir=source, dist_dir=dist)

    assert status.source_available is False
    assert status.stale is False
    assert status.reason == "no_source"


def test_inspect_webui_bundle_marks_missing_dist_stale(tmp_path: Path) -> None:
    source = tmp_path / "webui"
    dist = tmp_path / "cirno" / "web" / "dist"
    _touch(source / "package.json", mtime_ns=10)

    status = inspect_webui_bundle(source_dir=source, dist_dir=dist)

    assert status.source_available is True
    assert status.dist_available is False
    assert status.stale is True
    assert status.reason == "missing_dist"


def test_inspect_webui_bundle_detects_source_newer_than_dist(tmp_path: Path) -> None:
    source = tmp_path / "webui"
    dist = tmp_path / "cirno" / "web" / "dist"
    _touch(source / "package.json", mtime_ns=10)
    _touch(source / "src" / "App.tsx", mtime_ns=30)
    _touch(dist / "index.html", mtime_ns=20)

    status = inspect_webui_bundle(source_dir=source, dist_dir=dist)

    assert status.stale is True
    assert status.reason == "source_newer"
    assert status.newest_source == source / "src" / "App.tsx"


def test_inspect_webui_bundle_detects_channel_owned_ui_source(tmp_path: Path) -> None:
    source = tmp_path / "webui"
    dist = tmp_path / "cirno" / "web" / "dist"
    channel_ui = source / "channels" / "example" / "index.tsx"
    _touch(source / "package.json", mtime_ns=10)
    _touch(dist / "index.html", mtime_ns=20)
    _touch(channel_ui, mtime_ns=30)

    status = inspect_webui_bundle(source_dir=source, dist_dir=dist)

    assert status.needs_build is True
    assert status.reason == "source_newer"
    assert status.newest_source == channel_ui


def test_shared_notifications_make_existing_bundle_stale(tmp_path: Path) -> None:
    source = tmp_path / "webui"
    dist = tmp_path / "cirno/web/dist"
    shared = source / "packages/client-events/notifications.ts"
    _touch(source / "package.json", mtime_ns=10)
    _touch(dist / "index.html", mtime_ns=20)
    _touch(shared, mtime_ns=30)
    status = inspect_webui_bundle(source_dir=source, dist_dir=dist)
    assert status.needs_build
    assert status.newest_source == shared


def test_inspect_webui_bundle_accepts_fresh_dist(tmp_path: Path) -> None:
    source = tmp_path / "webui"
    dist = tmp_path / "cirno" / "web" / "dist"
    _touch(source / "package.json", mtime_ns=10)
    _touch(source / "src" / "App.tsx", mtime_ns=20)
    _touch(dist / "index.html", mtime_ns=30)

    status = inspect_webui_bundle(source_dir=source, dist_dir=dist)

    assert status.stale is False
    assert status.reason == "fresh"


def test_ensure_webui_bundle_auto_builds_stale_dist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("cirno_server.webui.build.bun_environment", lambda _: nullcontext({"PATH": "bun"}))
    source = tmp_path / "webui"
    dist = tmp_path / "cirno" / "web" / "dist"
    _touch(source / "package.json", mtime_ns=10)
    _touch(source / "src" / "App.tsx", mtime_ns=30)
    _touch(dist / "index.html", mtime_ns=20)
    commands: list[tuple[str, ...]] = []

    def fake_run(command, *, cwd: Path, check: bool, env: dict[str, str], timeout: int) -> None:
        commands.append(tuple(command))
        assert cwd == source
        assert check is True
        assert "PATH" in env
        assert timeout == 900
        if command == ["bun", "--bun", "run", "build"]:
            _touch(dist / "index.html", mtime_ns=40)

    status = ensure_webui_bundle(
        mode="auto",
        source_dir=source,
        dist_dir=dist,
        runner="bun",
        subprocess_run=fake_run,
    )

    assert status.stale is False
    assert commands == [("bun", "install", "--frozen-lockfile"),
                        ("bun", "--bun", "run", "build")]


def test_pick_webui_build_runner_returns_resolved_executable(monkeypatch) -> None:
    bun_shim = r"C:\tools\npm\bun.CMD"

    monkeypatch.setattr(
        "cirno_server.webui.build.shutil.which",
        lambda candidate: bun_shim if candidate == "bun" else None,
    )

    assert pick_webui_build_runner() == bun_shim


def test_ensure_webui_bundle_warns_without_building(tmp_path: Path) -> None:
    source = tmp_path / "webui"
    dist = tmp_path / "cirno" / "web" / "dist"
    _touch(source / "package.json", mtime_ns=10)
    _touch(source / "src" / "App.tsx", mtime_ns=30)
    _touch(dist / "index.html", mtime_ns=20)
    messages: list[str] = []

    status = ensure_webui_bundle(
        mode="warn",
        source_dir=source,
        dist_dir=dist,
        output=messages.append,
    )

    assert status.stale is True
    assert messages
    assert "Run `cd" in messages[0]


def test_build_prefers_existing_npm(monkeypatch):
    from cirno_server.webui.build import pick_webui_build_runner
    monkeypatch.setattr("cirno_server.webui.build.shutil.which", lambda name: "/tools/" + name)
    assert pick_webui_build_runner() == "/tools/npm"


def test_simultaneous_servers_share_one_bundle_build(tmp_path: Path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from cirno_server.webui.build import build_webui_bundle

    source = tmp_path / "webui"
    dist = tmp_path / "dist"
    _touch(source / "package.json", mtime_ns=10)
    _touch(source / "package-lock.json", mtime_ns=10)
    _touch(source / "src" / "App.tsx", mtime_ns=30)
    entered = Event()
    release = Event()
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if command[1] == "ci":
            entered.set()
            assert release.wait(2)
        else:
            _touch(dist / "index.html", mtime_ns=40)

    def build():
        return build_webui_bundle(source_dir=source, dist_dir=dist, runner="npm",
                                  subprocess_run=run, force=False)

    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(build)
        assert entered.wait(1)
        second = workers.submit(build)
        release.set()
        assert first.result(timeout=3).stale is False
        assert second.result(timeout=3).stale is False
    assert commands == [["npm", "ci"], ["npm", "run", "build"]]
