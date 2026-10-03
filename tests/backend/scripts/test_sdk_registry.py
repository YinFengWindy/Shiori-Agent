"""Retries may skip equal files, but never silently accept different published bytes."""

from __future__ import annotations

import base64
import hashlib
import urllib.error
from pathlib import Path

import pytest

from scripts import sdk_registry as registry


def test_new_npm_version_needs_upload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested = []

    def missing(url: str) -> None:
        requested.append(url)

    monkeypatch.setattr(registry, "registry_metadata", missing)
    assert registry.pending_files("npm", tmp_path, "3.1.0") == [
        tmp_path / "yinfengwindy-shiori-sdk-3.1.0.tgz"
    ]
    assert requested == ["https://registry.npmjs.org/@yinfengwindy%2Fshiori-sdk/3.1.0"]


def test_identical_npm_upload_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"verified tarball"
    (tmp_path / "yinfengwindy-shiori-sdk-3.1.0.tgz").write_bytes(content)
    digest = base64.b64encode(hashlib.sha512(content).digest()).decode()
    monkeypatch.setattr(
        registry,
        "registry_metadata",
        lambda _url: {"dist": {"integrity": f"sha512-{digest}"}},
    )
    assert registry.pending_files("npm", tmp_path, "3.1.0") == []


def test_conflicting_npm_version_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "yinfengwindy-shiori-sdk-3.1.0.tgz").write_bytes(b"new tarball")
    monkeypatch.setattr(
        registry,
        "registry_metadata",
        lambda _url: {"dist": {"integrity": "sha512-different"}},
    )
    with pytest.raises(ValueError, match="different content"):
        registry.pending_files("npm", tmp_path, "3.1.0")


def test_partial_pypi_release_only_uploads_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = tmp_path / "shiori_sdk-3.1.0-py3-none-any.whl"
    sdist = tmp_path / "shiori_sdk-3.1.0.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    monkeypatch.setattr(
        registry,
        "registry_metadata",
        lambda _url: {
            "urls": [
                {
                    "filename": wheel.name,
                    "digests": {"sha256": hashlib.sha256(b"wheel").hexdigest()},
                }
            ]
        },
    )
    assert registry.pending_files("pypi", tmp_path, "3.1.0") == [sdist]
    wheel.write_bytes(b"different wheel")
    with pytest.raises(ValueError, match="different content"):
        registry.pending_files("pypi", tmp_path, "3.1.0")


@pytest.mark.parametrize("code", [401, 403, 429, 500])
def test_registry_errors_are_not_treated_as_missing(
    code: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://example.invalid", code, "failure", {}, None
        )

    monkeypatch.setattr(registry.urllib.request, "urlopen", fail)
    with pytest.raises(urllib.error.HTTPError):
        registry.registry_metadata("https://example.invalid")


def test_missing_registry_version_is_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://example.invalid", 404, "missing", {}, None
        )

    monkeypatch.setattr(registry.urllib.request, "urlopen", missing)
    assert registry.registry_metadata("https://example.invalid") is None
