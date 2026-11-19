"""Unusable image references are text, not fatal transcript errors."""

from pathlib import Path

import pytest
from cirno_core.session.transcript.media import rewrite_local_markdown_images


@pytest.mark.parametrize("target", ["//[broken.png", "~missing-cirno-user/plot.png"])
def test_invalid_markdown_media_reference_keeps_the_reply(tmp_path, monkeypatch, target):
    if target.startswith("~"):
        expanduser = Path.expanduser

        def missing_user(path):
            if str(path).startswith("~missing-cirno-user"):
                raise RuntimeError("Could not determine home directory")
            return expanduser(path)

        monkeypatch.setattr(Path, "expanduser", missing_user)
    text = f"Research result. ![plot]({target})"
    assert rewrite_local_markdown_images(
        text, workspace_path=tmp_path,
        sign_path=lambda path: pytest.fail("Invalid media must not be signed"),
    ) == text


def test_bad_reference_does_not_hide_valid_media_or_allow_an_escape(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    image = project / "plot.png"
    image.write_bytes(b"image")
    (tmp_path / "outside.png").write_bytes(b"outside")
    text = "![bad](//[broken.png) ![plot](plot.png) ![outside](../outside.png)"
    signed = []

    def sign(path):
        signed.append(path)
        return {"url": "/v0/media/current/plot"}

    assert rewrite_local_markdown_images(text, workspace_path=project, sign_path=sign) == (
        "![bad](//[broken.png) ![plot](/v0/media/current/plot) ![outside](../outside.png)"
    )
    assert signed == [image.resolve()]
