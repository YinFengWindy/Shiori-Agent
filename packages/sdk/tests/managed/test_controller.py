"""Background lifecycle failures cannot replace the previous installed version."""

import asyncio
import hashlib
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from shiori_sdk.managed.artifacts import Artifact
from shiori_sdk.managed.controller import ManagedRuntime
from shiori_sdk.managed.installation import Installation
from shiori_sdk.managed.paths import native_path
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

    async def build(path, _resources):
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
    # The import is the user's original file: preparation never deletes it.
    assert controller.source.read_bytes()


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
    # A previous download left a verified cache; preparing reuses it offline.
    cached = install.root / "downloads" / "fixed.bin"
    cached.parent.mkdir()
    cached.write_bytes(b"runtime")
    original_build = runtime.build

    async def fail(_path, _resources):
        raise ValueError("build failed")

    runtime.build = fail
    runtime.submit("prepare")
    await runtime.task
    assert runtime.status()["error"] == "build failed"
    assert cached.is_file() and controller.previous.is_dir()
    runtime.build = original_build
    runtime.submit("prepare")
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


async def test_cancelled_removal_joins_its_thread_and_reports_the_outcome(
    controller, monkeypatch
):
    import threading

    from shiori_sdk.files.lease import exclusive_file_lease

    runtime, install = controller.runtime, controller.runtime.installation
    entered, release = threading.Event(), threading.Event()
    remove = install.remove

    def blocked_remove():
        entered.set()
        release.wait(10)
        remove()

    monkeypatch.setattr(install, "remove", blocked_remove)
    runtime.remove()
    try:
        await asyncio.to_thread(entered.wait, 10)
        cancelling = asyncio.create_task(runtime.cancel())
        await asyncio.sleep(0.05)
        # Cancellation waits: the thread still deletes under both leases.
        assert not cancelling.done()
        assert runtime.status()["busy"] is True
    finally:
        release.set()
    await cancelling
    status = runtime.status()
    assert status["busy"] is False and status["installed"] is False
    assert status["phase"] == "stopped"
    with exclusive_file_lease(install.root / "prepare.lock"):
        pass


async def test_kept_cache_is_reported_and_removable_without_an_installation(
    controller, tmp_path
):
    runtime, install = controller.runtime, controller.runtime.installation
    runtime.remove()
    await runtime.task

    async def fail(_path, _resources):
        raise ValueError("build failed")

    cached = install.root / "downloads" / "fixed.bin"
    cached.parent.mkdir()
    cached.write_bytes(b"runtime")
    runtime.build = fail
    runtime.submit("prepare")
    await runtime.task
    # Staging a killed host left behind is reported but never walked or sized.
    leftover = install.root / "s" / "killed" / "deep"
    leftover.mkdir(parents=True)
    (leftover / "partial.bin").write_bytes(b"x" * 4096)
    status = runtime.status()
    assert status["installed"] is False and status["staging"] is True
    assert status["reclaimable"] == len(b"runtime")
    runtime.remove()
    await runtime.task
    status = runtime.status()
    assert status["error"] == "" and status["reclaimable"] == 0
    assert status["staging"] is False
    assert not (install.root / "downloads").exists()


def test_reclaimable_probe_tolerates_entries_deleted_meanwhile(controller):
    install = controller.runtime.installation
    staging = install.root / "s"
    staging.mkdir(exist_ok=True)
    original = Path.stat

    def vanishing(path, *args, **kwargs):
        if path.name == "fixed.bin":
            raise FileNotFoundError(path)
        return original(path, *args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "stat", vanishing)
        assert install.reclaimable() == (0, False)


async def test_cancelled_removal_failure_is_recorded_and_still_cancels(
    controller, monkeypatch
):
    import threading

    runtime, install = controller.runtime, controller.runtime.installation
    entered, release = threading.Event(), threading.Event()

    def failing_remove():
        entered.set()
        release.wait(10)
        raise OSError("file in use")

    monkeypatch.setattr(install, "remove", failing_remove)
    runtime.remove()
    try:
        await asyncio.to_thread(entered.wait, 10)
        runtime.task.cancel()
    finally:
        release.set()
    await asyncio.gather(runtime.task, return_exceptions=True)
    assert runtime.task.cancelled()
    status = runtime.status()
    assert status["phase"] == "error" and status["error"] == "file in use"


async def test_cleanup_failure_after_publication_keeps_the_usable_phase(
    controller, monkeypatch
):
    runtime, install = controller.runtime, controller.runtime.installation

    def locked(**_kwargs):
        raise OSError("locked")

    monkeypatch.setattr(install, "discard_superseded", locked)
    runtime.submit("prepare", controller.source)
    await runtime.task
    assert runtime.phase == "ready"
    assert runtime.status()["error"] == "清理旧版本或下载缓存失败：locked"
    assert install.current() != controller.previous


async def test_custom_location_service_runs_with_state_in_plugin_data(
    tmp_path, monkeypatch
):
    import httpx

    import shiori_sdk.managed.controller as controller_module
    from shiori_sdk.managed import service

    monkeypatch.setattr(controller_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(controller_module.platform, "machine", lambda: "AMD64")
    tokens, launched = {}, []

    class Child:
        def __init__(self, _processes):
            self.process = None

        async def start(self, command, *, log, **_kwargs):
            self.process = SimpleNamespace(returncode=None)
            tokens[command[0]] = command[1]
            log.write_text("started", encoding="utf-8")

        async def close(self):
            self.process = None

    async def respond(request):
        return httpx.Response(200, json={"token": tokens[str(request.url.port)]})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(service, "OwnedChild", Child)
    monkeypatch.setattr(
        service.httpx,
        "AsyncClient",
        lambda **_kwargs: client_type(transport=httpx.MockTransport(respond)),
    )
    ctx = FakeServiceContext("test", tmp_path / "workspace")
    data = b"runtime"
    asset = Artifact(
        "fixed.bin",
        "https://example.test/fixed",
        len(data),
        hashlib.sha256(data).hexdigest(),
    )
    bundle = tmp_path / "fixed.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(asset.name, data)
    state = tmp_path / "workspace/plugin-data/test/runtime"

    def launch(path, port, token):
        launched.append(path)
        return [str(port), token], path, {}

    async def build(staging, _resources):
        (staging / "executable").write_bytes(b"ready")

    def create():
        return ManagedRuntime(
            Installation(state, "v1", [asset]),
            OwnedService(state, FakeProcesses(), launch),
            ctx.background,
            build,
            lambda: "managed",
        )

    runtime = create()
    runtime.relocate(tmp_path / "other-drive" / "test-runtime")
    runtime.submit("prepare", bundle)
    assert runtime.task is not None
    await runtime.task
    status = runtime.status()
    assert status["running"] is True and status["error"] == ""
    assert status["location"].endswith("test-runtime")
    install = native_path(tmp_path / "other-drive" / "test-runtime")
    assert launched[-1].parent == install / "v"
    assert runtime.service.root == native_path(state)
    await runtime.stop()
    assert sorted(item.name for item in native_path(state).iterdir()) == [
        "current.json",
        "location.json",
        "prepare.lock",
        "service.lock",
        "service.log",
    ]
    await runtime.close()
    # A new controller generation restores the location and starts again.
    again = create()
    assert again.status()["installed"] is True
    again.submit("start")
    assert again.task is not None
    await again.task
    assert again.status()["running"] is True and launched[-1] == launched[0]
    await again.close()
    await ctx.aclose()
