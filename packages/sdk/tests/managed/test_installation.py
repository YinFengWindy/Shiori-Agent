"""Atomic publication retains the prior runtime across failures and cancellation."""

import asyncio
import hashlib
import zipfile

import pytest

from shiori_sdk.managed.artifacts import Artifact
from shiori_sdk.managed.installation import Installation


def package(tmp_path):
    data = b"fixed package"
    resource = Artifact(
        "package.bin",
        "https://example.test/fixed",
        len(data),
        hashlib.sha256(data).hexdigest(),
    )
    source = tmp_path / "import.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(resource.name, data)
    return Installation(tmp_path / "runtime", "revision-1", [resource]), source


async def build(path):
    (path / "executable").write_bytes(b"ready")


async def test_build_failure_and_cancel_preserve_previous_pointer(tmp_path):
    installer, source = package(tmp_path)
    original = await installer.prepare(build, lambda *_: None, source=source)
    assert installer.current() is None
    installer.publish(original)

    async def fail(_path):
        raise ValueError("invalid runtime")

    with pytest.raises(ValueError, match="invalid runtime"):
        await installer.prepare(fail, lambda *_: None, source=source)
    assert installer.current() == original
    entered = asyncio.Event()

    async def pause(_path):
        entered.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(installer.prepare(pause, lambda *_: None, source=source))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert installer.current() == original
    assert not list((installer.root / "staging").iterdir())
    assert (original / "executable").read_bytes() == b"ready"


async def test_import_hash_failure_and_corrupt_receipt_cannot_be_current(tmp_path):
    installer, source = package(tmp_path)
    original = await installer.prepare(build, lambda *_: None, source=source)
    installer.publish(original)
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("package.bin", b"wrong package")
    with pytest.raises(ValueError, match="SHA-256"):
        await installer.prepare(build, lambda *_: None, source=source)
    assert installer.current() == original
    (original / "complete.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="记录校验"):
        installer.current()
