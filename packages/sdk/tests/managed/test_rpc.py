"""Runtime RPCs admit original imports by path and relocate only an empty install."""

import hashlib
import os
from pathlib import Path

import pytest

from shiori_sdk.managed.artifacts import Artifact
from shiori_sdk.managed.controller import ManagedRuntime
from shiori_sdk.managed.installation import Installation
from shiori_sdk.managed.paths import native_path
from shiori_sdk.managed.rpc import register_runtime_rpc
from shiori_sdk.managed.service import OwnedService
from shiori_sdk.testing.processes import FakeProcesses
from shiori_sdk.testing.service_context import FakeServiceContext

DATA = b"fixed archive"


@pytest.fixture
async def rpc(tmp_path, monkeypatch):
    import shiori_sdk.managed.controller as module

    monkeypatch.setattr(module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(module.platform, "machine", lambda: "AMD64")
    ctx = FakeServiceContext("sample", tmp_path / "workspace")
    asset = Artifact(
        "package.7z",
        "https://example.test/fixed",
        len(DATA),
        hashlib.sha256(DATA).hexdigest(),
    )
    root = tmp_path / "workspace/plugin-data/sample/runtime"

    async def build(staging, _resources):
        (staging / "executable").write_bytes(b"ready")

    runtime = ManagedRuntime(
        Installation(root, "v1", [asset]),
        OwnedService(root, FakeProcesses(), lambda path, port, token: ([], path, {})),
        ctx.background,
        build,
        lambda: "external",
        import_asset=asset.name,
    )
    register_runtime_rpc(
        ctx,
        runtime,
        namespace="sample-runtime",
        import_suffix=(".7z", ".zip"),
    )
    yield ctx.rpc.handlers, runtime
    await ctx.aclose()


async def test_import_by_original_path_validates_and_never_copies(rpc, tmp_path):
    handlers, runtime = rpc
    original = tmp_path / "user" / "package.7z"
    original.parent.mkdir()
    original.write_bytes(DATA)
    for invalid, message in [
        ("package.7z", "绝对路径"),
        (str(tmp_path / "user" / "package.rar"), "格式不受支持"),
        (str(tmp_path / "user" / "missing.7z"), "不存在"),
        (str(tmp_path / "user"), "格式不受支持"),
    ]:
        with pytest.raises(ValueError, match=message):
            await handlers["runtime.prepare"]({"source": invalid})
    (tmp_path / "user" / "folder.7z").mkdir()
    with pytest.raises(ValueError, match="普通文件"):
        await handlers["runtime.prepare"]({"source": str(tmp_path / "user/folder.7z")})
    short = tmp_path / "user" / "short.7z"
    short.write_bytes(DATA[:-1])
    with pytest.raises(ValueError, match="大小"):
        await handlers["runtime.prepare"]({"source": str(short)})
    await handlers["runtime.prepare"]({"source": str(original)})
    await runtime.task
    assert runtime.status()["installed"] is True and runtime.status()["error"] == ""
    assert original.read_bytes() == DATA
    workspace = tmp_path / "workspace"
    assert not (workspace / "private_runtime").exists()
    assert not [path for path in workspace.rglob("*.7z")]


async def test_relocate_uses_a_dedicated_directory_and_needs_an_empty_install(
    rpc, tmp_path
):
    handlers, runtime = rpc
    chosen = tmp_path / "D-drive"
    with pytest.raises(ValueError, match="不存在"):
        await handlers["runtime.relocate"]({"directory": str(chosen)})
    chosen.mkdir()
    status = await handlers["runtime.relocate"]({"directory": str(chosen)})
    assert native_path(chosen / "sample-runtime") == native_path(
        runtime.installation.install_root
    )
    assert status["relocatable"] is True
    # Picking the dedicated directory itself does not nest another one.
    (chosen / "sample-runtime").mkdir()
    await handlers["runtime.relocate"]({"directory": str(chosen / "sample-runtime")})
    assert runtime.installation.install_root == native_path(chosen / "sample-runtime")
    original = tmp_path / "package.7z"
    original.write_bytes(DATA)
    await handlers["runtime.prepare"]({"source": str(original)})
    await runtime.task
    status = await handlers["runtime.status"]({})
    assert status["installed"] is True and status["relocatable"] is False
    with pytest.raises(RuntimeError, match="请先删除环境"):
        await handlers["runtime.relocate"]({"directory": str(tmp_path)})
    await handlers["runtime.remove"]({})
    await runtime.task
    assert not (chosen / "sample-runtime").exists()
    assert (await handlers["runtime.status"]({}))["relocatable"] is True


async def test_corrupt_import_keeps_relocation_and_removal_available(rpc, tmp_path):
    handlers, runtime = rpc
    (tmp_path / "chosen").mkdir()
    await handlers["runtime.relocate"]({"directory": str(tmp_path / "chosen")})
    corrupt = tmp_path / "package.7z"
    corrupt.write_bytes(DATA[:-1] + b"X")
    await handlers["runtime.prepare"]({"source": str(corrupt)})
    await runtime.task
    status = await handlers["runtime.status"]({})
    assert "SHA-256" in status["error"]
    assert status["relocatable"] is True and status["removable"] is False
    # A failed build's leftovers block relocation, so removal must be offered.
    (native_path(tmp_path / "chosen/sample-runtime") / "tmp").mkdir()
    await handlers["runtime.prepare"]({"source": str(corrupt)})
    await runtime.task
    status = await handlers["runtime.status"]({})
    assert status["relocatable"] is False and status["removable"] is True
    await handlers["runtime.remove"]({})
    await runtime.task
    status = await handlers["runtime.status"]({})
    assert status["relocatable"] is True and status["removable"] is False


async def test_unreadable_location_is_reported_and_reset(rpc, tmp_path):
    handlers, runtime = rpc
    runtime.installation.root.mkdir(parents=True)
    runtime.installation.location.write_text("[]", encoding="utf-8")
    status = await handlers["runtime.status"]({})
    assert "位置记录无效" in status["error"] and status["location"] == ""
    assert status["relocatable"] is True and status["removable"] is True
    status = await handlers["runtime.relocate"]({})
    assert status["error"] == "" and status["customized"] is False
    assert native_path(Path(status["location"])) == runtime.installation.root


async def test_relocate_accepts_only_local_directories_and_restores_default(
    rpc, tmp_path
):
    handlers, runtime = rpc
    if os.name == "nt":
        for remote in (r"\\server\share", r"\\?\C:\Envs", r"\\.\C:\Envs"):
            with pytest.raises(ValueError, match="本机磁盘"):
                await handlers["runtime.relocate"]({"directory": remote})
        # The dedicated directory matches the namespace case-insensitively.
        (tmp_path / "Sample-Runtime").mkdir()
        await handlers["runtime.relocate"](
            {"directory": str(tmp_path / "Sample-Runtime")}
        )
        assert runtime.installation.install_root == native_path(
            tmp_path / "Sample-Runtime"
        )
    else:
        (tmp_path / "chosen").mkdir()
        await handlers["runtime.relocate"]({"directory": str(tmp_path / "chosen")})
    assert (await handlers["runtime.status"]({}))["customized"] is True
    status = await handlers["runtime.relocate"]({})
    assert status["customized"] is False
    assert runtime.installation.install_root == runtime.installation.root


@pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-only")
async def test_import_through_a_junction_is_rejected(rpc, tmp_path):
    import _winapi

    handlers, _runtime = rpc
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "package.7z").write_bytes(DATA)
    _winapi.CreateJunction(str(tmp_path / "real"), str(tmp_path / "linked"))
    with pytest.raises(ValueError, match="链接"):
        await handlers["runtime.prepare"](
            {"source": str(tmp_path / "linked/package.7z")}
        )
