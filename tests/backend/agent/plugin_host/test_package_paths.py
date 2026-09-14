"""Portable path boundary rejection without depending on the current OS."""

import os
import subprocess

import pytest

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.package_paths import contained_file, package_path


@pytest.mark.parametrize(
    "value",
    [
        "../escape.py",
        "/root.py",
        "C:/escape.py",
        "C:escape.py",
        "backend\\plugin.py",
        "backend/../plugin.py",
        "backend//plugin.py",
        "backend/plugin.py:stream",
        "CON.py",
        "NUL",
        "a./b",
        "a /b",
        "a\x00b",
        "//host/file",
        "./plugin.py",
    ],
)
def test_rejects_nonportable_paths(value):
    with pytest.raises(PackageContractError) as caught:
        package_path(value, "entry")
    assert caught.value.diagnostic.code == "invalid_path"
    assert caught.value.diagnostic.field == "entry"


def test_rejects_required_directory_instead_of_file(tmp_path):
    (tmp_path / "directory").mkdir()
    with pytest.raises(PackageContractError, match="regular file"):
        contained_file(tmp_path, "directory", "entry")


def test_rejects_symlink_outside_package(tmp_path):
    root = tmp_path / "package"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "entry.py").write_text("", encoding="utf-8")
    link = root / "linked"
    if os.name == "nt":
        # Junctions exercise Windows path resolution without symlink privilege.
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            check=True,
            capture_output=True,
        )
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(PackageContractError) as caught:
            contained_file(root, "linked/entry.py", "entry")
        assert caught.value.diagnostic.code == "outside_package"
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()
