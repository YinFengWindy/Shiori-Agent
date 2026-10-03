"""Release archives must preserve publishable metadata and their verified bytes."""

from __future__ import annotations

import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import sdk_release as release


def test_npm_tarball_uses_the_public_personal_scope() -> None:
    assert release.NPM_PACKAGE_NAME == "@yinfengwindy/shiori-sdk"
    assert release.npm_tarball_name("3.1.0") == "yinfengwindy-shiori-sdk-3.1.0.tgz"


def _tar(path: Path, files: dict[str, bytes]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    sdk = tmp_path / "packages/sdk"
    (sdk / "python/shiori_sdk").mkdir(parents=True)
    (sdk / "python/shiori_sdk/_version.py").write_text(
        '__version__ = "3.1.0"\n', encoding="utf-8"
    )
    (sdk / "package.json").write_text('{"version":"3.1.0"}', encoding="utf-8")
    (sdk / "LICENSE").write_bytes(b"MIT license text")
    (tmp_path / "LICENSE").write_bytes(b"MIT license text")
    return tmp_path


@pytest.fixture
def archives(tmp_path: Path) -> Path:
    directory = tmp_path / "artifacts"
    directory.mkdir()
    manifest = {
        "name": "@yinfengwindy/shiori-sdk",
        "version": "3.1.0",
        "license": "MIT",
        "repository": {"url": f"git+{release.REPOSITORY_URL}.git"},
        "publishConfig": {"access": "public"},
        "exports": {
            name: {"types": "./dist/index.d.ts", "import": "./dist/index.js"}
            for name in (".", "./contract", "./host-internal", "./testing")
        },
    }
    _tar(
        directory / "yinfengwindy-shiori-sdk-3.1.0.tgz",
        {
            "package/package.json": json.dumps(manifest).encode(),
            "package/LICENSE": b"MIT license text",
            "package/README.md": b"SDK usage",
            "package/dist/index.js": b"export {};",
            "package/dist/index.d.ts": b"export {};",
        },
    )
    metadata = (
        "Metadata-Version: 2.4\nName: shiori-sdk\nVersion: 3.1.0\n"
        "License-Expression: MIT\nDescription-Content-Type: text/markdown\n"
        f"Project-URL: Repository, {release.REPOSITORY_URL}\n\nSDK usage\n"
    ).encode()
    with zipfile.ZipFile(directory / "shiori_sdk-3.1.0-py3-none-any.whl", "w") as wheel:
        wheel.writestr("shiori_sdk-3.1.0.dist-info/METADATA", metadata)
        wheel.writestr(
            "shiori_sdk-3.1.0.dist-info/licenses/LICENSE", b"MIT license text"
        )
        wheel.writestr("shiori_sdk/py.typed", b"")
    _tar(
        directory / "shiori_sdk-3.1.0.tar.gz",
        {
            f"shiori_sdk-3.1.0/{name}": data
            for name, data in {
                "PKG-INFO": metadata,
                "LICENSE": b"MIT license text",
                "README.md": b"SDK usage",
                "pyproject.toml": b"[project]",
                "python/shiori_sdk/_version.py": b'__version__ = "3.1.0"',
            }.items()
        },
    )
    return directory


@pytest.mark.parametrize(
    "ref", ["refs/heads/main", "refs/pull/1/merge", "refs/tags/sdk-v3.1.0"]
)
def test_version_accepts_dry_run_or_exact_release_tag(
    repository: Path, ref: str
) -> None:
    assert release.release_version(repository, ref) == "3.1.0"


@pytest.mark.parametrize("tag", ["v3.1.0", "sdk-v3.2.0", "sdk-v3.1.0-rc.1"])
def test_release_rejects_wrong_tag(repository: Path, tag: str) -> None:
    with pytest.raises(ValueError, match="Tag must"):
        release.release_version(repository, f"refs/tags/{tag}")


def test_release_rejects_version_drift(repository: Path) -> None:
    (repository / "packages/sdk/package.json").write_text(
        '{"version":"3.0.0"}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="versions differ"):
        release.release_version(repository, "refs/heads/main")


def test_release_rejects_stale_package_license(repository: Path) -> None:
    (repository / "packages/sdk/LICENSE").write_bytes(b"Old license")
    with pytest.raises(ValueError, match="LICENSE must match"):
        release.release_version(repository, "refs/heads/main")


def test_valid_archives_include_both_registries(
    repository: Path, archives: Path
) -> None:
    manifest = release.release_manifest(
        archives, repository, "refs/tags/sdk-v3.1.0", "a" * 40
    )
    assert manifest["version"] == "3.1.0"
    assert set(manifest["sha256"]) == {
        "yinfengwindy-shiori-sdk-3.1.0.tgz",
        "shiori_sdk-3.1.0.tar.gz",
        "shiori_sdk-3.1.0-py3-none-any.whl",
    }


def test_npm_pack_source_exports_are_rejected(archives: Path) -> None:
    path = archives / "yinfengwindy-shiori-sdk-3.1.0.tgz"
    files = release._tar_contents(path)
    manifest = json.loads(files["package/package.json"])
    manifest["exports"]["."] = "./src/index.ts"
    files["package/package.json"] = json.dumps(manifest).encode()
    _tar(path, files)
    with pytest.raises(ValueError, match="Pack with pnpm"):
        release.validate_archives(archives, "3.1.0", b"MIT license text")


def test_sdist_without_license_is_rejected(archives: Path) -> None:
    path = archives / "shiori_sdk-3.1.0.tar.gz"
    files = release._tar_contents(path)
    del files["shiori_sdk-3.1.0/LICENSE"]
    _tar(path, files)
    with pytest.raises(KeyError, match="LICENSE"):
        release.validate_archives(archives, "3.1.0", b"MIT license text")


def test_linux_artifacts_verify_from_windows_checkout(
    repository: Path, archives: Path
) -> None:
    linux_license = b"MIT\nlicense text\n"
    for name in ("yinfengwindy-shiori-sdk-3.1.0.tgz", "shiori_sdk-3.1.0.tar.gz"):
        path = archives / name
        files = release._tar_contents(path)
        license_path = next(name for name in files if name.endswith("/LICENSE"))
        files[license_path] = linux_license
        _tar(path, files)
    path = archives / "shiori_sdk-3.1.0-py3-none-any.whl"
    with zipfile.ZipFile(path) as wheel:
        contents = {name: wheel.read(name) for name in wheel.namelist()}
    contents["shiori_sdk-3.1.0.dist-info/licenses/LICENSE"] = linux_license
    with zipfile.ZipFile(path, "w") as wheel:
        for name, data in contents.items():
            wheel.writestr(name, data)
    windows_license = linux_license.replace(b"\n", b"\r\n")
    (repository / "LICENSE").write_bytes(windows_license)
    (repository / "packages/sdk/LICENSE").write_bytes(windows_license)
    manifest = release.release_manifest(
        archives, repository, "refs/heads/main", "a" * 40
    )
    (repository / "LICENSE").write_bytes(linux_license)
    (repository / "packages/sdk/LICENSE").write_bytes(linux_license)
    assert (
        release.release_manifest(archives, repository, "refs/heads/main", "a" * 40)
        == manifest
    )


def test_download_verification_rejects_changed_bytes(
    repository: Path, archives: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release, "REPOSITORY", repository)
    command = [
        "sdk_release",
        "seal",
        str(archives),
        "--ref",
        "refs/tags/sdk-v3.1.0",
        "--commit",
        "a" * 40,
    ]
    monkeypatch.setattr(sys, "argv", command)
    release.main()
    path = archives / "yinfengwindy-shiori-sdk-3.1.0.tgz"
    files = release._tar_contents(path)
    files["package/README.md"] = b"Changed after verification"
    _tar(path, files)
    command[1] = "verify"
    with pytest.raises(ValueError, match="no longer match"):
        release.main()
    command[1] = "seal"
    with pytest.raises(FileExistsError):
        release.main()
