"""Untrusted archives cannot escape staging or allocate unbounded payloads."""

import stat
import sys
import zipfile
import pytest

from plugins.pet_2d.backend.package_archive import stage_archive
from plugins.desktop_pet.backend.provider_files import resolve_staged_zip


def test_rejects_path_traversal_and_windows_aliases_before_extraction(
    tmp_path, avatar_package
):
    for name in (
        "../outside",
        "package/../../outside",
        "C:/outside",
        "package/CON.txt",
        "package/dir./file",
        "package/dir\\file",
        "/outside",
    ):
        source = avatar_package.write(extra={name: b"bad"})
        destination = tmp_path / "extract"
        with pytest.raises(ValueError, match="路径"):
            stage_archive(source, destination)
        assert not destination.exists()
    assert not (tmp_path.parent / "outside").exists()


def test_duplicate_casefold_names_and_symlinks_are_refused(tmp_path, avatar_package):
    source = avatar_package.write(extra={"package/SOURCE.PNG": b"alias"})
    with pytest.raises(ValueError, match="重复路径"):
        stage_archive(source, tmp_path / "duplicate")
    source = avatar_package.write()
    info = zipfile.ZipInfo("package/escape")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(source, "a") as archive:
        archive.writestr(info, "../../outside")
    with pytest.raises(ValueError, match="链接"):
        stage_archive(source, tmp_path / "symlink")


def test_declared_payload_tampering_and_unlisted_files_are_refused(
    tmp_path, avatar_package
):
    source = avatar_package.write(
        lambda manifest: manifest["files"]["source.png"].update(sha256="0" * 64)
    )
    with pytest.raises(ValueError, match="完整性"):
        stage_archive(source, tmp_path / "hash")
    source = avatar_package.write(extra={"package/extra.json": b"{}"})
    with pytest.raises(ValueError, match="清单与 ZIP"):
        stage_archive(source, tmp_path / "unlisted")


def test_expanded_size_is_rejected_before_opening_entries(
    tmp_path, avatar_package, monkeypatch
):
    source = avatar_package.write()
    import plugins.pet_2d.backend.package_archive as module

    monkeypatch.setattr(module, "MAX_EXPANDED_BYTES", 32)
    with pytest.raises(ValueError, match="展开后超过"):
        stage_archive(source, tmp_path / "oversized")
    assert not (tmp_path / "oversized").exists()


def _directory_link(target, link):
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def test_native_staging_and_target_junctions_cannot_cross_ownership(
    tmp_path, avatar_package
):
    source = avatar_package.write()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "avatar.zip").write_bytes(source.read_bytes())
    staging = source.parent / "escape"
    _directory_link(outside, staging)
    with pytest.raises(ValueError, match="原生文件选择"):
        resolve_staged_zip(
            tmp_path,
            str(staging / "avatar.zip"),
            namespace="pet_2d-pets",
            max_bytes=1024 * 1024,
        )
    with pytest.raises(ValueError, match="原生文件选择"):
        resolve_staged_zip(
            tmp_path,
            str(outside / "avatar.zip"),
            namespace="pet_2d-pets",
            max_bytes=1024 * 1024,
        )
    from plugins.pet_2d.backend.storage import role_directory

    link_root = tmp_path / "plugin-data"
    _directory_link(outside, link_root)
    with pytest.raises(ValueError, match="越界"):
        role_directory(tmp_path, "one", create=True)
    assert not (outside / "pet_2d").exists()
