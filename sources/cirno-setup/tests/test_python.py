"""Shared uv install semantics and index migration."""

from cirno_setup.python import environment, package_command


def test_explicit_uv_index_wins_over_legacy_pip_configuration():
    values = {"PIP_INDEX_URL": "https://legacy.invalid/simple", "UV_INDEX_URL": "https://selected.invalid/simple", "HTTPS_PROXY": "http://proxy.invalid"}
    result = environment(values)
    assert result["UV_INDEX_URL"] == values["UV_INDEX_URL"]
    assert result["HTTPS_PROXY"] == values["HTTPS_PROXY"]
    assert environment({"PIP_INDEX_URL": values["PIP_INDEX_URL"]})["UV_INDEX_URL"] == values["PIP_INDEX_URL"]


def test_legacy_cli_reinstall_options_use_the_selected_python():
    assert package_command("install", "/agent env/bin/python", ["--force-reinstall", "--no-cache-dir", "demo"]) == [
        "uv", "pip", "install", "--python", "/agent env/bin/python", "--reinstall", "--no-cache", "demo",
    ]


def test_install_keeps_selected_roots_compatible_when_later_packages_need_backtracking(tmp_path, monkeypatch):
    """A local wheel index reproduces the Manim/Marker shared-dependency conflict."""
    import subprocess
    import zipfile
    from pathlib import Path

    from cirno_setup.backends import pip
    from cirno_setup.context import Context
    from cirno_setup.initialize import initialize
    from cirno_setup.policy import Policy
    from cirno_setup.recipe import Recipe

    wheels = tmp_path / "wheels"
    wheels.mkdir()

    def wheel(name, version, dependencies=()):
        dist = f"{name}-{version}.dist-info"
        # Synthetic releases are written in one clock tick. Distinct source
        # sizes prevent a prior release's timestamp-based .pyc being reused.
        files = {
            f"{name}.py": f"version = {version!r}\n# {'release ' * int(version.split('.')[0])}\n",
            f"{dist}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
                + "".join(f"Requires-Dist: {requirement}\n" for requirement in dependencies),
            f"{dist}/WHEEL": "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        }
        files[f"{dist}/RECORD"] = "".join(f"{file},,\n" for file in files)
        with zipfile.ZipFile(wheels / f"{name}-{version}-py3-none-any.whl", "w") as archive:
            for file, content in files.items():
                archive.writestr(file, content)

    wheel("shared_image", "1.0")
    wheel("shared_image", "2.0")
    wheel("animation_tool", "1.0", ("shared_image<2",))
    wheel("animation_tool", "2.0", ("shared_image>=2",))
    wheel("document_tool", "1.0", ("shared_image<2",))
    context = Context(tmp_path / "home", Path(__file__).parents[1] / "src/cirno_setup/assets", Policy())
    initialize(context)
    run = context.run

    def offline(arguments, **kwargs):
        assert arguments[:3] == ["uv", "pip", "install"]
        return run([*arguments, "--no-index", "--find-links", str(wheels)], **kwargs)

    monkeypatch.setattr(context, "run", offline)
    animation = Recipe("pip", ("animation_tool",), imports=("animation_tool",))
    document = Recipe("pip", ("document_tool",), imports=("document_tool",))
    pip.install(context, animation)
    assert pip.verify(context, animation).ready
    result = context.inspect([str(context.python), "-c", "import animation_tool; print(animation_tool.version)"])
    assert result.stdout.strip() == "2.0"
    pip.install(context, document)
    result = subprocess.run(["uv", "pip", "check", "--python", str(context.python)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    result = context.inspect([str(context.python), "-c", "import animation_tool, document_tool, shared_image; assert animation_tool.version == shared_image.version == '1.0'"])
    assert result.returncode == 0, result.stderr
