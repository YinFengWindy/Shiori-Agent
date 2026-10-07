"""Background lifecycle failures cannot replace the previous installed version."""

import asyncio
import hashlib
import zipfile
from types import SimpleNamespace

import pytest

from shiori_sdk.managed.artifacts import Artifact
from shiori_sdk.managed.controller import ManagedRuntime
from shiori_sdk.managed.installation import Installation
from shiori_sdk.managed.service import OwnedService
from shiori_sdk.testing.processes import FakeProcesses
from shiori_sdk.testing.service_context import FakeServiceContext


class Service(OwnedService):
    def __init__(self, root):
        super().__init__(
            root, FakeProcesses(), lambda path, port, token: ([], path, {})
        )
        self.started = asyncio.Event()
        self.failure = False
        self.hold = False
        self.stopped = 0

    async def start(self, installation, *, timeout=180):
        self.started.set()
        if self.hold:
            try:
                await asyncio.Event().wait()
            finally:
                await self.close()
        if self.failure:
            raise RuntimeError("startup failed")
        self.url = "http://127.0.0.1:12345"

    async def close(self):
        self.stopped += 1
        self.url = None


@pytest.fixture
async def controller(tmp_path, monkeypatch):
    import shiori_sdk.managed.controller as module

    monkeypatch.setattr(module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(module.platform, "machine", lambda: "AMD64")
    ctx = FakeServiceContext("test", tmp_path)
    data = b"runtime"
    asset = Artifact(
        "fixed.bin",
        "https://example.test/fixed",
        len(data),
        hashlib.sha256(data).hexdigest(),
    )
    source = tmp_path / "fixed.zip"
    with zipfile.ZipFile(source, "w") as bundle:
        bundle.writestr(asset.name, data)
    install = Installation(tmp_path / "runtime", "v1", [asset])

    async def build(path):
        (path / "executable").write_bytes(b"ready")

    previous = await install.prepare(build, lambda *_: None, source=source)
    install.publish(previous)
    child = Service(install.root)
    runtime = ManagedRuntime(install, child, ctx.background, build, lambda: "managed")
    yield SimpleNamespace(
        runtime=runtime, child=child, previous=previous, source=source
    )
    await runtime.close()
    await ctx.aclose()


async def test_start_failure_keeps_previous_installation_and_reports_error(controller):
    runtime = controller.runtime
    controller.child.failure = True
    runtime.submit("prepare", controller.source)
    await runtime.task
    assert runtime.status()["phase"] == "error"
    assert runtime.status()["error"] == "startup failed"
    assert runtime.installation.current() == controller.previous
    assert not controller.source.exists()


async def test_disable_during_start_cancels_and_joins_before_marking_closed(controller):
    runtime = controller.runtime
    controller.child.hold = True
    runtime.submit("start")
    await controller.child.started.wait()
    await runtime.close()
    assert runtime.task.done()
    assert controller.child.stopped >= 1
    assert runtime.installation.current() == controller.previous
    with pytest.raises(RuntimeError, match="其他操作"):
        runtime.submit("start")


async def test_prepare_repairs_invalid_current_record_instead_of_blocking_itself(
    controller,
):
    runtime = controller.runtime
    runtime.installation.pointer.write_text("{}", encoding="utf-8")
    assert runtime.status()["installed"] is False
    assert "记录无效" in runtime.status()["error"]
    runtime.submit("start")
    await runtime.task
    assert runtime.status()["phase"] == "error"
    runtime.submit("prepare", controller.source)
    await runtime.task
    assert runtime.status()["error"] == ""
    assert runtime.installation.current() != controller.previous


async def test_success_prunes_cache_and_old_versions_but_failure_keeps_cache(
    controller, tmp_path
):
    runtime, install = controller.runtime, controller.runtime.installation
    cached = install.root / "downloads" / "fixed.bin"
    assert cached.is_file() and controller.previous.is_dir()
    import_copy = tmp_path / "again.zip"
    import_copy.write_bytes(controller.source.read_bytes())
    original_build = runtime.build

    async def fail(_path):
        raise ValueError("build failed")

    runtime.build = fail
    runtime.submit("prepare", controller.source)
    await runtime.task
    assert runtime.status()["error"] == "build failed"
    assert cached.is_file() and controller.previous.is_dir()
    runtime.build = original_build
    runtime.submit("prepare", import_copy)
    await runtime.task
    current = install.current()
    assert runtime.status()["error"] == "" and current != controller.previous
    assert not (install.root / "downloads").exists()
    assert list((install.root / "v").iterdir()) == [current]


async def test_remove_requires_idle_stopped_runtime_then_deletes_everything(
    controller,
):
    from shiori_sdk.files.lease import exclusive_file_lease

    runtime, install = controller.runtime, controller.runtime.installation
    (install.root / "prepare.log").write_text("previous run", encoding="utf-8")
    controller.child.hold = True
    runtime.submit("start")
    await controller.child.started.wait()
    with pytest.raises(RuntimeError, match="其他操作"):
        runtime.remove()
    await runtime.cancel()
    controller.child.child.process = SimpleNamespace(returncode=None)
    with pytest.raises(RuntimeError, match="请先停止环境"):
        runtime.remove()
    controller.child.child.process = None
    # Another generation's service still holds the service lease.
    with exclusive_file_lease(install.root / "service.lock"):
        runtime.remove()
        await runtime.task
    assert runtime.status()["error"] == "托管服务正在运行，请先停止环境"
    assert install.current() == controller.previous
    runtime.remove()
    await runtime.task
    status = runtime.status()
    assert status["phase"] == "stopped" and status["installed"] is False
    assert sorted(item.name for item in install.root.iterdir()) == [
        "prepare.lock",
        "prepare.log",
        "service.lock",
    ]
