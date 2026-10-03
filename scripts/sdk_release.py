"""Validate and seal the exact SDK archives passed between release jobs."""

from __future__ import annotations

import argparse
import email.parser
import hashlib
import json
import re
import tarfile
import zipfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
REPOSITORY_URL = "https://github.com/YinFengWindy/Shiori-Agent"


def _license_content(raw: bytes) -> bytes:
    # Git may use CRLF in Windows checkouts while CI archives contain LF.
    # Archive checksums remain byte-exact; only source/license comparison normalizes.
    return raw.replace(b"\r\n", b"\n")


def release_version(repository: Path, ref: str) -> str:
    """Require synchronized stable versions and an exact SDK tag when given a tag."""
    sdk = repository / "packages/sdk"
    source = (sdk / "python/shiori_sdk/_version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', source, re.MULTILINE)
    if not match or not re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", match[1]
    ):
        raise ValueError("SDK releases require a stable X.Y.Z version")
    version = match[1]
    manifest = json.loads((sdk / "package.json").read_text(encoding="utf-8"))
    if manifest["version"] != version:
        raise ValueError("Python and npm SDK versions differ")
    if ref.startswith("refs/tags/") and ref != f"refs/tags/sdk-v{version}":
        raise ValueError(f"Tag must be sdk-v{version}")
    if _license_content((sdk / "LICENSE").read_bytes()) != _license_content(
        (repository / "LICENSE").read_bytes()
    ):
        raise ValueError("SDK LICENSE must match the repository LICENSE")
    return version


def _tar_contents(path: Path) -> dict[str, bytes]:
    with tarfile.open(path, "r:gz") as archive:
        files = {}
        for member in archive.getmembers():
            if member.isfile():
                handle = archive.extractfile(member)
                if handle is None or member.name in files:
                    raise ValueError(
                        f"Invalid or duplicate archive member: {member.name}"
                    )
                files[member.name] = handle.read()
        return files


def _python_metadata(raw: bytes, version: str) -> None:
    metadata = email.parser.BytesParser().parsebytes(raw)
    expected = {
        "Name": "shiori-sdk",
        "Version": version,
        "License-Expression": "MIT",
        "Description-Content-Type": "text/markdown",
    }
    for key, value in expected.items():
        if metadata[key] != value:
            raise ValueError(f"Invalid Python {key}: {metadata[key]!r}")
    if "Repository, " + REPOSITORY_URL not in metadata.get_all("Project-URL", []):
        raise ValueError("Python artifact is missing its repository URL")
    description = metadata.get_payload()
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Python artifact is missing its README")


def validate_archives(directory: Path, version: str, license_text: bytes) -> list[Path]:
    """Inspect package identities, published entries and distributable license files."""
    license_text = _license_content(license_text)
    npm = directory / f"shiori-sdk-{version}.tgz"
    wheel = directory / f"shiori_sdk-{version}-py3-none-any.whl"
    sdist = directory / f"shiori_sdk-{version}.tar.gz"
    paths = [npm, wheel, sdist]
    expected = {path.name for path in paths} | {"manifest.json"}
    if any(path.name not in expected for path in directory.iterdir()):
        raise ValueError("Release directory contains unexpected files")

    files = _tar_contents(npm)
    manifest = json.loads(files["package/package.json"])
    if (manifest["name"], manifest["version"], manifest.get("license")) != (
        "@shiori/sdk",
        version,
        "MIT",
    ):
        raise ValueError("Invalid npm identity or license")
    if manifest.get("repository", {}).get("url") != f"git+{REPOSITORY_URL}.git":
        raise ValueError("npm repository URL must match the trusted publisher")
    if manifest.get("publishConfig", {}).get("access") != "public":
        raise ValueError("npm SDK must publish publicly")
    exports = manifest["exports"]
    if set(exports) != {".", "./contract", "./host-internal", "./testing"}:
        raise ValueError("npm SDK exports are incomplete")
    for entry in exports.values():
        if not isinstance(entry, dict) or set(entry) != {"types", "import"}:
            raise ValueError("Pack with pnpm: npm exports must target built entries")
        for target in entry.values():
            if not target.startswith("./dist/") or f"package/{target[2:]}" not in files:
                raise ValueError(f"Missing compiled npm export: {target}")
    if (
        _license_content(files["package/LICENSE"]) != license_text
        or not files["package/README.md"]
    ):
        raise ValueError("npm artifact is missing the current license or README")

    with zipfile.ZipFile(wheel) as archive:
        info = f"shiori_sdk-{version}.dist-info"
        _python_metadata(archive.read(f"{info}/METADATA"), version)
        if _license_content(archive.read(f"{info}/licenses/LICENSE")) != license_text:
            raise ValueError("Wheel license differs from the source license")
        archive.read("shiori_sdk/py.typed")
    files = _tar_contents(sdist)
    prefix = f"shiori_sdk-{version}"
    _python_metadata(files[f"{prefix}/PKG-INFO"], version)
    if _license_content(files[f"{prefix}/LICENSE"]) != license_text:
        raise ValueError("Source distribution license differs from the source license")
    for name in ("README.md", "pyproject.toml", "python/shiori_sdk/_version.py"):
        if not files[f"{prefix}/{name}"]:
            raise ValueError(f"Source distribution is missing {name}")
    return paths


def release_manifest(directory: Path, repository: Path, ref: str, commit: str) -> dict:
    """Bind validated archives to their source commit and SHA-256 checksums."""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected a full Git commit SHA")
    version = release_version(repository, ref)
    paths = validate_archives(directory, version, (repository / "LICENSE").read_bytes())
    return {
        "version": version,
        "commit": commit,
        "sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
        },
    }


def main() -> None:
    """Create a build manifest or verify downloaded artifacts before publication."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["seal", "verify"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    manifest = release_manifest(args.directory, REPOSITORY, args.ref, args.commit)
    path = args.directory / "manifest.json"
    if args.command == "seal":
        # Re-sealing must not bless a different build under the same run artifact.
        with path.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
    elif json.loads(path.read_text(encoding="utf-8")) != manifest:
        raise ValueError("Release archives no longer match the build manifest")
    print(f"Validated SDK {manifest['version']} from {manifest['commit']}")


if __name__ == "__main__":
    main()
