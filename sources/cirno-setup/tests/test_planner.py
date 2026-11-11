"""Dependency graph, presets, namespaced packages and interruption semantics."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cirno_setup import backends
from cirno_setup.context import Context
from cirno_setup.planner import plan
from cirno_setup.policy import Policy
from cirno_setup.recipe import Recipe, Verification
from cirno_setup.registry import catalogue, resolve
from cirno_setup.runner import ensure


@pytest.fixture
def context(tmp_path):
    home = tmp_path / "home"
    (home / ".cirno").mkdir(parents=True)
    assets = Path(__file__).parents[1] / "src/cirno_setup/assets"
    return Context(home, assets, Policy())


def test_dependency_order_is_stable_and_shared_dependencies_install_once(context):
    entries = {"pip.a": Recipe("pip", ("a",)),
               "pip.b": Recipe("pip", ("b",), ("pip.a",)),
               "presets.test": Recipe(dependencies=("pip.b", "pip.a"))}
    assert [step.name for step in plan(context, ["+presets.test", "+pip.b"], entries)] == ["pip.a", "pip.b"]


def test_cycles_and_unknown_items_fail_before_installation(context):
    entries = {"system.a": Recipe(dependencies=("system.b",)),
               "system.b": Recipe(dependencies=("system.a",))}
    with pytest.raises(ValueError, match="system.a -> system.b -> system.a"):
        plan(context, ["system.a"], entries)
    with pytest.raises(ValueError, match="Unknown setup component"):
        plan(context, ["+presets.unknown"])
    assert not context.root.exists()


def test_personal_preset_retains_office_latex_tools_and_channel(context):
    names = [step.name for step in plan(context, ["+presets.rachebtms"])]
    assert {"system.libreoffice", "system.latex", "pip.pytest", "tools.chromium", "tools.xurl",
            "tools.nvm", "channels.telegram", "memory.embedding", "memory.bge_small_zh"} <= set(names)
    assert len(names) == len(set(names))
    assert names.index("tools.node") < names.index("npm.summarize")
    assert names.index("system.browser") < names.index("tools.chromium")
    assert plan(context, []) == []
    with pytest.raises(ValueError):
        resolve("+full")


def test_personal_preset_short_name_shares_the_canonical_plan(context):
    expected = plan(context, ["+presets.rachebtms"])
    assert plan(context, ["+rachebtms"]) == expected
    assert plan(context, ["+rachebtms", "+presets.rachebtms"]) == expected


@pytest.mark.parametrize("selector", ["+pip.--evil", "+brew.--evil", "+apt.--evil", "+npm.;id", "+../evil"])
def test_package_selectors_cannot_be_options_or_shell_code(selector):
    with pytest.raises(ValueError):
        resolve(selector)


def test_scoped_npm_alias_and_custom_package_backends():
    assert resolve("+npm.summarize").packages == ("@steipete/summarize@0.26.0",)
    assert resolve("+pip.example-package").packages == ("example-package",)
    assert resolve("+brew.example").dependencies == ("tools.homebrew",)
    assert resolve("+apt.hello=2.0").packages == ("hello=2.0",)


def test_failed_component_resumes_without_reinstalling_completed_work(context, monkeypatch):
    entries = {"pip.a": Recipe("pip", ("a",)), "pip.b": Recipe("pip", ("b",), ("pip.a",))}
    calls = []
    fail = True

    def install(ctx, recipe):
        calls.append(recipe.packages[0])
        if recipe.packages == ("b",) and fail:
            raise RuntimeError("network interrupted")
        (ctx.home / recipe.packages[0]).touch()

    backend = SimpleNamespace(install=install, verify=lambda ctx, recipe: Verification((ctx.home / recipe.packages[0]).exists()))
    monkeypatch.setattr(backends, "backend", lambda name: backend)
    monkeypatch.setattr("cirno_setup.runner.os.geteuid", lambda: 1000)
    steps = plan(context, ["pip.b"], entries)
    with pytest.raises(RuntimeError, match="network interrupted"):
        ensure(context, [], steps=steps)
    state = json.loads((context.root / "setup.json").read_text())
    assert state["status"] == "failed" and set(state["completed"]) == {"pip.a"}
    fail = False
    ensure(context, [], steps=steps)
    assert calls == ["a", "b", "b"]
    (context.home / "a").unlink()
    ensure(context, [], steps=steps)
    assert calls == ["a", "b", "b", "a"]


def test_empty_selection_does_not_install(context, monkeypatch):
    monkeypatch.setattr(backends, "backend", lambda name: pytest.fail("disabled setup touched a backend"))
    ensure(context, [])
    assert not context.root.exists()


def test_final_verification_rechecks_reused_and_new_components_after_installation(context, monkeypatch):
    entries = {"pip.a": Recipe("pip", ("a",)), "pip.b": Recipe("pip", ("b",))}
    installed = {"a"}
    events = []

    def verify(ctx, recipe):
        name = recipe.packages[0]
        events.append(("verify", name))
        return Verification(name in installed)

    def install(ctx, recipe):
        name = recipe.packages[0]
        events.append(("install", name))
        installed.add(name)

    monkeypatch.setattr(backends, "backend", lambda _: SimpleNamespace(verify=verify, install=install))
    monkeypatch.setattr("cirno_setup.runner.os.geteuid", lambda: 1000)
    ensure(context, [], steps=plan(context, list(entries), entries), verify_after=True)
    assert events == [("verify", "a"), ("verify", "b"), ("install", "b"), ("verify", "b"),
                      ("verify", "a"), ("verify", "b")]
    assert json.loads((context.root / "setup.json").read_text())["status"] == "ready"


def test_final_verification_detects_dependencies_broken_by_a_later_install(context, monkeypatch):
    entries = {"pip.a": Recipe("pip", ("a",)), "pip.b": Recipe("pip", ("b",))}
    installed = {"a"}

    def install(ctx, recipe):
        installed.discard("a")
        installed.add(recipe.packages[0])

    backend = SimpleNamespace(install=install, verify=lambda ctx, recipe:
                              Verification(recipe.packages[0] in installed, "dependency conflict"))
    monkeypatch.setattr(backends, "backend", lambda _: backend)
    monkeypatch.setattr("cirno_setup.runner.os.geteuid", lambda: 1000)
    with pytest.raises(RuntimeError, match="pip.a final verification failed: dependency conflict"):
        ensure(context, [], steps=plan(context, list(entries), entries), verify_after=True)
    state = json.loads((context.root / "setup.json").read_text())
    assert state["status"] == "failed" and state["component"] == "pip.a"
    assert "pip.a" not in state["completed"]


def test_root_commands_do_not_inherit_user_code_paths(context, monkeypatch):
    monkeypatch.setattr("cirno_setup.context.os.geteuid", lambda: 0)
    monkeypatch.setenv("BASH_ENV", "/untrusted/start.sh")
    monkeypatch.setenv("PYTHONPATH", "/untrusted/python")
    env = context.environment()
    assert env["PATH"] == "/usr/bin:/bin"
    assert "BASH_ENV" not in env and "PYTHONPATH" not in env



def test_catalogue_is_data_only_and_every_dependency_resolves(context):
    for name in catalogue():
        plan(context, [name])
