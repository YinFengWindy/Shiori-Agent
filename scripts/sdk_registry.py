"""Stage unpublished SDK files, rejecting registry collisions on retries."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path


def registry_metadata(url: str) -> dict | None:
    """Return public metadata; only HTTP 404 means that a version is unpublished."""
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def pending_files(registry: str, directory: Path, version: str) -> list[Path]:
    """Skip identical published bytes and fail before uploading conflicting files."""
    if registry == "npm":
        tarball = directory / f"shiori-sdk-{version}.tgz"
        metadata = registry_metadata(
            f"https://registry.npmjs.org/@shiori%2fsdk/{version}"
        )
        if metadata is None:
            return [tarball]
        digest = base64.b64encode(
            hashlib.sha512(tarball.read_bytes()).digest()
        ).decode()
        if metadata["dist"].get("integrity") != f"sha512-{digest}":
            raise ValueError(f"npm {version} already exists with different content")
        return []

    metadata = registry_metadata(f"https://pypi.org/pypi/shiori-sdk/{version}/json")
    existing = {item["filename"]: item for item in metadata["urls"]} if metadata else {}
    pending = []
    for path in sorted([*directory.glob("*.whl"), *directory.glob("*.tar.gz")]):
        remote = existing.get(path.name)
        if remote is None:
            pending.append(path)
        elif (
            remote["digests"]["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            raise ValueError(f"PyPI {path.name} already exists with different content")
    return pending


def main() -> None:
    """Prepare an empty upload directory using only previously verified archives."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", choices=["npm", "pypi"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    manifest = json.loads(
        (args.directory / "manifest.json").read_text(encoding="utf-8")
    )
    paths = pending_files(args.registry, args.directory, manifest["version"])
    # A fresh directory ensures upload globbing cannot include stale packages.
    args.destination.mkdir(parents=True, exist_ok=False)
    for path in paths:
        shutil.copyfile(path, args.destination / path.name)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"pending={'true' if paths else 'false'}\n")
    print(f"{args.registry}: {len(paths)} file(s) need publication")


if __name__ == "__main__":
    main()
