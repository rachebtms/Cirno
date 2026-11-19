"""Strict existence resolution cannot replace the path that passed policy checks."""

import pytest
from cirno_core.security import workspace_policy as policy


@pytest.mark.parametrize("permission", ["workspace", "extra-root", "exact-file"])
@pytest.mark.parametrize("changed", ["leaf", "ancestor"])
@pytest.mark.parametrize("strict", [False, True])
def test_resolution_rejects_a_path_retargeted_after_authorization(tmp_path, monkeypatch, permission, changed, strict):
    workspace, media, outside = [tmp_path / name for name in ("workspace", "media", "outside")]
    for folder in (workspace, media, outside):
        folder.mkdir()
    parent = (workspace if permission == "workspace" else media) / "results"
    parent.mkdir()
    source, secret = parent / "paper.txt", outside / "paper.txt"
    source.write_text("Allowed file")
    secret.write_text("Outside secret")
    options = {"extra_allowed_roots": [media]} if permission == "extra-root" else (
        {"extra_allowed_files": [source]} if permission == "exact-file" else {}
    )
    allowed = policy.is_path_allowed
    swapped = False

    def retarget_after_check(path, roots):
        nonlocal swapped
        result = allowed(path, roots)
        if not swapped:
            swapped = True
            if changed == "leaf":
                source.unlink()
                source.symlink_to(secret)
            else:
                parent.rename(parent.with_name("original-results"))
                parent.symlink_to(outside, target_is_directory=True)
        return result

    monkeypatch.setattr(policy, "is_path_allowed", retarget_after_check)
    with pytest.raises(policy.WorkspaceBoundaryError, match="changed|outside"):
        policy.resolve_allowed_path(source, workspace=workspace, allowed_root=workspace, strict=strict, **options)
    assert secret.read_text() == "Outside secret"


def test_stable_in_workspace_symlink_and_missing_path_keep_existing_behavior(tmp_path):
    folder = tmp_path / "results"
    folder.mkdir()
    source = folder / "paper.txt"
    source.write_text("Allowed file")
    link = tmp_path / "linked.txt"
    link.symlink_to(source)
    assert policy.resolve_allowed_path(link, workspace=tmp_path, allowed_root=tmp_path, strict=True) == source
    with pytest.raises(FileNotFoundError):
        policy.resolve_allowed_path(folder / "missing.txt", workspace=tmp_path, allowed_root=tmp_path, strict=True)
