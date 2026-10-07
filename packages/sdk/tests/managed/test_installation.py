"""Atomic publication retains the prior runtime across failures and cancellation."""

import asyncio
import hashlib
import json
import os
import zipfile
from pathlib import Path

import pytest

from shiori_sdk.managed.artifacts import Artifact
from shiori_sdk.managed.installation import Installation
from shiori_sdk.managed.paths import native_path


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


async def build(path, _resources):
    (path / "executable").write_bytes(b"ready")


async def test_build_failure_and_cancel_preserve_previous_pointer(tmp_path):
    installer, source = package(tmp_path)
    original = await installer.prepare(build, lambda *_: None, source=source)
    assert installer.current() is None
    installer.publish(original)

    async def fail(_path, _resources):
        raise ValueError("invalid runtime")

    with pytest.raises(ValueError, match="invalid runtime"):
        await installer.prepare(fail, lambda *_: None, source=source)
    assert installer.current() == original
    entered = asyncio.Event()

    async def pause(_path, _resources):
        entered.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(installer.prepare(pause, lambda *_: None, source=source))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert installer.current() == original
    assert not (installer.root / "s").exists()
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


async def test_previous_trial_pointer_remains_readable_after_compact_layout(tmp_path):
    installer, source = package(tmp_path)
    original = await installer.prepare(build, lambda *_: None, source=source)
    installer.publish(original)
    pointer = json.loads(installer.pointer.read_text(encoding="utf-8"))
    previous = installer.root / "versions" / original.name
    previous.parent.mkdir()
    original.rename(previous)
    del pointer["layout"]
    installer.pointer.write_text(json.dumps(pointer), encoding="utf-8")
    assert installer.current() == previous
    for invalid in ("outside", {"unexpected": "object"}):
        pointer["layout"] = invalid
        installer.pointer.write_text(json.dumps(pointer), encoding="utf-8")
        with pytest.raises(ValueError, match="布局无效"):
            installer.current()


async def test_insufficient_space_fails_before_any_copy(tmp_path, monkeypatch):
    import shiori_sdk.managed.installation as module

    installer, source = package(tmp_path)
    installer.installed_size = 5 * module.GIB
    usage = module.shutil.disk_usage(tmp_path)
    monkeypatch.setattr(
        module.shutil,
        "disk_usage",
        lambda _path: usage._replace(free=6 * module.GIB),
    )
    built = []

    async def record(path, _resources):
        built.append(path)

    # 5 GiB installed + 13 artifact bytes + the 1 GiB minimum margin > 6 GiB.
    with pytest.raises(
        RuntimeError, match=r"磁盘空间不足：需要约 6\.0 GiB，剩余 6\.0 GiB"
    ):
        await installer.prepare(record, lambda *_: None, source=source)
    assert not (installer.root / "downloads").exists()
    assert not built and installer.current() is None
    installer.installed_size = 4 * module.GIB
    installer.publish(await installer.prepare(record, lambda *_: None, source=source))


def single(tmp_path, data=b"fixed archive"):
    """An installation whose only artifact is imported as an original file."""
    resource = Artifact(
        "package.7z",
        "https://example.test/fixed",
        len(data),
        hashlib.sha256(data).hexdigest(),
    )
    return Installation(tmp_path / "state", "revision-1", [resource]), resource


async def test_custom_location_holds_artifacts_and_persists_across_instances(
    tmp_path,
):
    installer, source = package(tmp_path)
    other = tmp_path / "other-drive" / "runtime"
    installer.relocate(other)
    version = await installer.prepare(build, lambda *_: None, source=source)
    installer.publish(version)
    assert version.parent == installer.install_root / "v"
    assert installer.install_root == native_path(other)
    # Only small state lives in plugin data; nothing large follows it there.
    assert sorted(item.name for item in installer.root.iterdir()) == [
        "current.json",
        "location.json",
        "prepare.lock",
    ]
    again = Installation(tmp_path / "runtime", "revision-1", installer.artifacts)
    assert again.install_root == native_path(other)
    assert again.current() == version


async def test_location_changes_only_while_nothing_is_installed_or_kept(tmp_path):
    installer, source = package(tmp_path)
    installer.publish(await installer.prepare(build, lambda *_: None, source=source))
    with pytest.raises(RuntimeError, match="请先删除环境"):
        installer.relocate(tmp_path / "elsewhere")
    installer.remove()
    # A kept download cache is also something a removal would delete.
    (installer.root / "downloads").mkdir()
    (installer.root / "downloads" / "package.bin.part").write_bytes(b"fix")
    with pytest.raises(RuntimeError, match="请先删除环境"):
        installer.relocate(tmp_path / "elsewhere")
    installer.remove()
    installer.relocate(tmp_path / "elsewhere")
    assert installer.install_root == native_path(tmp_path / "elsewhere")
    # A target already holding installation entries is never adopted.
    (tmp_path / "taken" / "v").mkdir(parents=True)
    with pytest.raises(ValueError, match="已有环境文件"):
        installer.relocate(tmp_path / "taken")


async def test_original_import_is_read_in_place_without_any_copy(tmp_path):
    installer, resource = single(tmp_path)
    original = tmp_path / "user" / "package.7z"
    original.parent.mkdir()
    original.write_bytes(b"fixed archive")
    installer.relocate(tmp_path / "install")
    seen = {}

    async def consume(staging, resources):
        seen.update(resources)
        assert not (staging / "downloads").exists()
        (staging / "executable").write_bytes(b"ready")

    installer.publish(
        await installer.prepare(
            consume, lambda *_: None, source=original, import_asset=resource.name
        )
    )
    assert seen == {resource.name: original}
    assert original.read_bytes() == b"fixed archive"
    copies = [
        path
        for path in (tmp_path / "install").rglob("*")
        if path.is_file() and path.stat().st_size == resource.size
    ]
    assert copies == [] and not (installer.root / "downloads").exists()


async def test_original_with_wrong_hash_is_rejected_before_the_build(tmp_path):
    installer, resource = single(tmp_path)
    original = tmp_path / "package.7z"
    original.write_bytes(b"fixed archivX")
    built = []

    async def record(staging, _resources):
        built.append(staging)

    with pytest.raises(ValueError, match="SHA-256"):
        await installer.prepare(
            record, lambda *_: None, source=original, import_asset=resource.name
        )
    assert not built and installer.current() is None
    assert not (installer.install_root / "s").exists()
    assert not (installer.install_root / "v").exists()
    assert original.read_bytes() == b"fixed archivX"


async def test_space_check_uses_the_install_root_volume(tmp_path, monkeypatch):
    import shiori_sdk.managed.installation as module

    installer, source = package(tmp_path)
    installer.installed_size = 5 * module.GIB
    install = tmp_path / "large-drive"
    installer.relocate(install)
    usage = module.shutil.disk_usage(tmp_path)

    def disk_usage(path):
        # Plugin data sits on a full system drive; the chosen drive has room.
        large = native_path(Path(path)).is_relative_to(native_path(install))
        return usage._replace(free=(100 if large else 1) * module.GIB)

    monkeypatch.setattr(module.shutil, "disk_usage", disk_usage)
    installer.publish(await installer.prepare(build, lambda *_: None, source=source))
    assert module.free_space(installer.install_root) == 100 * module.GIB
    installer.remove()
    installer.relocate(tmp_path / "runtime")
    with pytest.raises(RuntimeError, match="磁盘空间不足"):
        await installer.prepare(build, lambda *_: None, source=source)


async def test_remove_deletes_install_root_entries_and_keeps_state(tmp_path):
    installer, source = package(tmp_path)
    installer = Installation(
        installer.root, "revision-1", installer.artifacts, scratch=("hf",)
    )
    install = tmp_path / "chosen" / "runtime"
    installer.relocate(install)
    installer.publish(await installer.prepare(build, lambda *_: None, source=source))
    for name in ("tmp", "cache", "hf", "downloads"):
        (install / name).mkdir(exist_ok=True)
        (install / name / "large.bin").write_bytes(b"x")
    (installer.root / "prepare.log").write_text("log", encoding="utf-8")
    (installer.root / "tts-config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "chosen" / "user-file.txt").write_text("mine", encoding="utf-8")
    installer.remove()
    assert not install.exists()
    assert (tmp_path / "chosen" / "user-file.txt").is_file()
    assert sorted(item.name for item in installer.root.iterdir()) == [
        "location.json",
        "prepare.lock",
        "prepare.log",
        "tts-config.json",
    ]
    assert installer.current() is None and not installer.occupied()


async def test_default_install_survives_moving_plugin_data(tmp_path):
    installer, source = package(tmp_path)
    version = await installer.prepare(build, lambda *_: None, source=source)
    installer.publish(version)
    moved = tmp_path / "moved" / "runtime"
    moved.parent.mkdir()
    installer.root.rename(moved)
    again = Installation(moved, "revision-1", installer.artifacts)
    assert again.current() == native_path(moved) / "v" / version.name


async def test_failed_import_leaves_nothing_that_blocks_relocation(tmp_path):
    installer, resource = single(tmp_path)
    installer.relocate(tmp_path / "chosen")
    original = tmp_path / "package.7z"
    original.write_bytes(b"fixed archivX")

    async def unreachable(_staging, _resources):
        raise AssertionError("build after a failed verification")

    with pytest.raises(ValueError, match="SHA-256"):
        await installer.prepare(
            unreachable, lambda *_: None, source=original, import_asset=resource.name
        )
    assert not installer.occupied()
    installer.relocate(tmp_path / "elsewhere")
    # Whatever a failed build leaves behind both blocks relocation and is removable.
    (installer.install_root / "tmp").mkdir(parents=True)
    assert installer.occupied()
    installer.remove()
    assert not installer.occupied()
    installer.relocate(None)
    assert installer.install_root == installer.root


async def test_unreadable_location_can_be_reset_without_reading_it(tmp_path):
    installer, source = package(tmp_path)
    installer.root.mkdir(parents=True)
    installer.location.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        _ = installer.install_root
    # Nothing is installed: choosing a location overwrites the broken record.
    installer.relocate(tmp_path / "chosen")
    assert installer.install_root == native_path(tmp_path / "chosen")
    installer.publish(await installer.prepare(build, lambda *_: None, source=source))
    installer.location.write_text('{"root": "relative"}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="请先删除环境"):
        installer.relocate(None)
    # Removal resets the record; files at the lost location cannot be found.
    installer.remove()
    assert installer.install_root == installer.root and not installer.occupied()


@pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-only")
async def test_removal_unlinks_junctions_without_entering_them(tmp_path):
    import _winapi

    installer, source = package(tmp_path)
    installer.publish(await installer.prepare(build, lambda *_: None, source=source))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.bin").write_bytes(b"keep")
    _winapi.CreateJunction(str(outside), str(tmp_path / "runtime" / "cache"))
    _winapi.CreateJunction(str(outside), str(tmp_path / "runtime" / "v" / "linked"))
    installer.remove()
    assert not (tmp_path / "runtime" / "cache").exists()
    assert (outside / "keep.bin").read_bytes() == b"keep"
    assert installer.current() is None and not installer.occupied()
