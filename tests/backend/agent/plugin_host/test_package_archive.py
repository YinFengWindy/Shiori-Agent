"""Zip validation shares directory semantics while rejecting unsafe archive names."""

import stat
from zipfile import ZipFile, ZipInfo

import pytest

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.package_archive import validate_package_zip


def test_validates_root_layout_package_without_installing(contract_package, tmp_path):
    archive = tmp_path / "demo.zip"
    with ZipFile(archive, "w") as output:
        for path in contract_package.rglob("*"):
            if path.is_file():
                output.write(path, path.relative_to(contract_package).as_posix())
    result = validate_package_zip(archive)
    assert result.manifest.id == "external_demo"
    assert len(result.renderer) == 3


@pytest.mark.parametrize(
    "name",
    ["../escape", "/absolute", "C:/drive", "backend\\plugin.py", "entry.py:stream"],
)
def test_rejects_zip_traversal_before_extraction(tmp_path, name):
    archive = tmp_path / "bad.zip"
    with ZipFile(archive, "w") as output:
        member = ZipInfo(name)
        # Windows ZipInfo normalizes backslashes at construction; preserve the
        # actual unsafe central-directory spelling a Unix-produced zip can have.
        member.filename = name
        output.writestr(member, "bad")
    with pytest.raises(PackageContractError) as caught:
        validate_package_zip(archive)
    assert caught.value.diagnostic.code == "invalid_path"
    assert not (tmp_path / "escape").exists()


def test_rejects_wrapping_directory(tmp_path):
    archive = tmp_path / "bad.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("plugin/manifest.yaml", "api: 2")
    with pytest.raises(PackageContractError) as caught:
        validate_package_zip(archive)
    assert caught.value.diagnostic.code == "invalid_layout"


def test_rejects_case_collisions(tmp_path):
    archive = tmp_path / "bad.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("manifest.yaml", "api: 2")
        output.writestr("Manifest.yaml", "api: 2")
    with pytest.raises(PackageContractError) as caught:
        validate_package_zip(archive)
    assert caught.value.diagnostic.code == "duplicate_path"


def test_rejects_symlink_members(tmp_path):
    archive = tmp_path / "bad.zip"
    with ZipFile(archive, "w") as output:
        member = ZipInfo("backend/plugin.py")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        output.writestr(member, "../../outside.py")
    with pytest.raises(PackageContractError) as caught:
        validate_package_zip(archive)
    assert caught.value.diagnostic.code == "unsupported_member"
