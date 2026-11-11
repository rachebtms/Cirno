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
