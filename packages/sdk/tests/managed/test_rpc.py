"""Runtime RPCs admit original imports by path and relocate only an empty install."""

import hashlib

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
    )
    register_runtime_rpc(
        ctx,
        runtime,
        namespace="sample-runtime",
        import_suffix=(".7z", ".zip"),
        import_asset=asset.name,
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
