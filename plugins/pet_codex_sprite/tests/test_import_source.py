"""Public pet imports accept only the plugin's native selection staging."""

from pathlib import Path
import sys

import pytest

from plugins.pet_codex_sprite.backend.import_source import resolve_package_import_source


def test_import_source_accepts_staged_zip_and_rejects_arbitrary_or_invalid_sources(
    tmp_path,
):
    staging = tmp_path / "private_runtime" / "imports" / "pet_codex_sprite-pets"
    staging.mkdir(parents=True)
    selected = staging / "selected.ZIP"
    selected.write_bytes(b"PK")
    assert resolve_package_import_source(tmp_path, str(selected)) == selected.resolve()
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"PK")
    with pytest.raises(ValueError, match="原生文件选择"):
        resolve_package_import_source(tmp_path, str(outside))
    with pytest.raises(ValueError, match="原生文件选择"):
        resolve_package_import_source(
            tmp_path, str(staging / ".." / "pet_codex_sprite-pets" / selected.name)
        )
    with pytest.raises(ValueError, match="原生文件选择"):
        resolve_package_import_source(tmp_path, "relative.zip")
    wrong = staging / "image.png"
    wrong.write_bytes(b"image")
    directory = staging / "directory.zip"
    directory.mkdir()
    for source in (wrong, directory):
        with pytest.raises(ValueError, match="普通 ZIP"):
            resolve_package_import_source(tmp_path, str(source))
    large = staging / "large.zip"
    with large.open("wb") as stream:
        stream.truncate(32 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="超过 32MB"):
        resolve_package_import_source(tmp_path, str(large))


def _directory_link(target: Path, link: Path) -> None:
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def test_import_source_rejects_namespace_or_file_symlink_escape(tmp_path):
    staging = tmp_path / "private_runtime" / "imports" / "pet_codex_sprite-pets"
    staging.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "selected.zip").write_bytes(b"PK")
    escaped_directory = staging / "escaped"
    _directory_link(outside, escaped_directory)
    with pytest.raises(ValueError, match="原生文件选择"):
        resolve_package_import_source(tmp_path, str(escaped_directory / "selected.zip"))
    # Use a second workspace to exercise replacement of the namespace itself.
    workspace = tmp_path / "second"
    redirected = workspace / "private_runtime" / "imports" / "pet_codex_sprite-pets"
    redirected.parent.mkdir(parents=True)
    _directory_link(outside, redirected)
    with pytest.raises(ValueError, match="暂存目录越界"):
        resolve_package_import_source(workspace, str(redirected / "selected.zip"))
