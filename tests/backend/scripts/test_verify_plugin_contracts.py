"""Failure proofs for the production plugin lifecycle contract runner."""

import asyncio
import gc
from pathlib import Path

import pytest

from agent.plugin_host.unload import PluginReloadFailed
from desktop_bridge.plugin_rpc.rpc import PluginRpcRegistry
from shiori_sdk.kernel import Kernel
from tests.support.plugin_contracts import profile_for, verify_contract


def _package(tmp_path: Path, source: str, fields: str = "") -> Path:
    package = tmp_path / "natural_chat"
    package.mkdir()
    (package / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: natural_chat\nentry: plugin.py\n" + fields,
        encoding="utf-8",
    )
    (package / "plugin.py").write_text(source, encoding="utf-8")
    return package


async def test_declared_provider_must_be_published_by_real_setup(tmp_path):
    package = _package(
        tmp_path, "async def setup(ctx): pass\n", "provides: [reply_policy]\n"
    )
    with pytest.raises(AssertionError):
        await verify_contract("natural_chat", tmp_path / "workspace", directory=package)


async def test_bare_task_leak_fails_before_emergency_cleanup(tmp_path):
    package = _package(
        tmp_path,
        "import asyncio\nasync def setup(ctx):\n"
        "    asyncio.create_task(asyncio.Event().wait())\n",
    )
    with pytest.raises(AssertionError, match="task outlived disposal"):
        await verify_contract("natural_chat", tmp_path / "workspace", directory=package)


async def test_same_effect_count_in_another_order_is_rejected(tmp_path):
    package = _package(
        tmp_path,
        "from shiori_sdk.core.services import KV\n"
        "async def setup(ctx):\n"
        "    count = ctx.require(KV).increment('setups')\n"
        "    for name in (('first', 'second') if count == 1 else ('second', 'first')):\n"
        "        ctx.effect(name, lambda: None)\n",
        "inject: [kv]\n",
    )
    with pytest.raises(AssertionError):
        await verify_contract("natural_chat", tmp_path / "workspace", directory=package)


async def test_missing_production_rpc_withdrawal_is_detected(tmp_path, monkeypatch):
    package = _package(
        tmp_path,
        "from shiori_sdk.core.services import RPC\n"
        "async def ping(payload): return payload\n"
        "async def setup(ctx): ctx.require(RPC).register('ping', ping)\n",
        "inject: [rpc]\n",
    )
    monkeypatch.setattr(PluginRpcRegistry, "unregister", lambda *_: None)
    with pytest.raises(PluginReloadFailed):
        await verify_contract("natural_chat", tmp_path / "workspace", directory=package)


async def test_generated_method_without_an_executed_registration_is_rejected(tmp_path):
    package = _package(
        tmp_path,
        "from shiori_sdk.core.services import RPC\n"
        "async def ping(payload): return payload\n"
        "async def setup(ctx): ctx.require(RPC).register('ping', ping)\n",
        "inject: [rpc]\n",
    )
    with pytest.raises(AssertionError, match="RPC registration coverage"):
        await verify_contract(
            "natural_chat",
            tmp_path / "workspace",
            directory=package,
            rpc_contract={"methods": ["ping", "uncovered"], "services": []},
        )


async def test_stale_dependent_export_is_rejected(tmp_path, monkeypatch):
    package = _package(tmp_path, "async def setup(ctx): pass\n")
    activate = Kernel.activate
    previous = {}

    async def stale_activate(kernel, plugin_id):
        result = await activate(kernel, plugin_id)
        if plugin_id == "contract_consumer":
            key = "plugin:contract_consumer"
            if key in previous:
                kernel._providers[key] = previous[key]
            else:
                previous[key] = kernel._providers[key]
        return result

    monkeypatch.setattr(Kernel, "activate", stale_activate)
    with pytest.raises(AssertionError, match="dependent was not set up again"):
        await verify_contract("natural_chat", tmp_path / "workspace", directory=package)


async def test_restart_only_plugin_cannot_silently_reload(tmp_path, monkeypatch):
    package = _package(
        tmp_path, "async def setup(ctx): pass\n", "supports_hot_unload: false\n"
    )
    monkeypatch.setattr(Kernel, "restart_only", lambda *_: None)
    with pytest.raises(AssertionError, match="restart-only closure was replaced"):
        await verify_contract("natural_chat", tmp_path / "workspace", directory=package)


async def test_database_leak_is_detected_before_fixture_teardown(tmp_path):
    package = _package(
        tmp_path,
        "import sqlite3\nfrom shiori_sdk.core.services import WORKSPACE\n"
        "async def setup(ctx):\n"
        "    connection = sqlite3.connect(ctx.require(WORKSPACE) / 'unclosed.db')\n"
        "    ctx.expose(connection)\n",
        "inject: [workspace]\n",
    )
    with pytest.raises(AssertionError, match="SQLite connection outlived disposal"):
        await verify_contract("natural_chat", tmp_path / "workspace", directory=package)


async def test_swallowed_external_io_still_fails_the_contract(tmp_path):
    package = _package(
        tmp_path,
        "import socket, subprocess\n"
        "async def setup(ctx):\n"
        "    with socket.socket() as connection:\n"
        "        try: connection.connect(('127.0.0.1', 1))\n"
        "        except Exception: pass\n"
        "    try: subprocess.Popen(['never-executed'])\n"
        "    except Exception: pass\n",
    )
    with pytest.raises(AssertionError, match="Unexpected network/process"):
        await verify_contract("natural_chat", tmp_path / "workspace", directory=package)


@pytest.mark.parametrize(
    "fields",
    [
        "inject: [rpc, processes]\n",
        "inject: [rpc]\noptional_dependencies: [observe]\n",
        "inject: [rpc]\nconflicts: [observe]\n",
    ],
)
def test_rpc_profile_cannot_hide_resource_or_dependency_requirements(tmp_path, fields):
    package = _package(tmp_path, "async def setup(ctx): pass\n", fields)
    (package / "tests").mkdir()
    (package / "tests/contract.json").write_text('{"profile":"rpc"}', encoding="utf-8")
    with pytest.raises(AssertionError, match="only supports"):
        profile_for(package)


async def test_gc_finalizer_does_not_change_browser_setup_task_order(
    tmp_path, monkeypatch
):
    """Ambient finalizers collected in setup are not plugin-authored work."""
    from agent.tools.plugin_capability import PluginTools

    finalized = asyncio.Event()
    closed, deferred_closed = asyncio.Event(), asyncio.Event()

    class PreviousClient:
        def __del__(self):
            loop = asyncio.get_running_loop()
            loop.create_task(self.aclose())
            loop.call_soon(loop.create_task, self.deferred_aclose())

        async def aclose(self):
            closed.set()

        async def deferred_aclose(self):
            deferred_closed.set()

    async def previous_generator():
        try:
            yield
        finally:
            finalized.set()

    original = PluginTools.for_plugin
    collect_once = True

    def collect_in_setup(self, binding):
        nonlocal collect_once
        if binding.plugin_id == "browser_use" and collect_once:
            collect_once = False
            gc.collect()
        return original(self, binding)

    monkeypatch.setattr(PluginTools, "for_plugin", collect_in_setup)
    automatic_gc = gc.isenabled()
    gc.disable()
    generator = previous_generator()
    await generator.__anext__()
    cycle: list[object] = [generator, PreviousClient()]
    cycle.append(cycle)
    del generator, cycle
    callbacks_before = tuple(gc.callbacks)
    try:
        await verify_contract("browser_use", tmp_path / "workspace")
        assert finalized.is_set()
        assert closed.is_set()
        assert deferred_closed.is_set()
    finally:
        gc.collect()
        if automatic_gc:
            gc.enable()
        assert tuple(gc.callbacks) == callbacks_before


@pytest.mark.parametrize("finalizer", ["asyncgen", "gc_destructor"])
async def test_finalizer_cleanup_still_fails_for_leaks_and_exceptions(finalizer):
    """Excluding ownership must not exclude a finalizer from all-task checks."""
    from tests.support.plugin_contract_observation import _ACTIVATING, observe_lifecycle

    started, release = asyncio.Event(), asyncio.Event()

    async def cleanup():
        started.set()
        await release.wait()
        raise RuntimeError("ambient cleanup failed")

    async def previous_generator():
        try:
            yield
        finally:
            await cleanup()

    class PreviousClient:
        def __del__(self):
            asyncio.get_running_loop().create_task(cleanup())

    # Model collection interrupting another plugin's activation. The asyncgen
    # case releases the last reference directly, outside cyclic GC callbacks.
    token = _ACTIVATING.set("unrelated_plugin")
    with observe_lifecycle() as observation:
        try:
            if finalizer == "asyncgen":
                generator = previous_generator()
                await generator.__anext__()
                del generator
            else:
                cycle: list[object] = [PreviousClient()]
                cycle.append(cycle)
                del cycle
                gc.collect()
            assert _ACTIVATING.get() == "unrelated_plugin"
            async with asyncio.timeout(1):
                await started.wait()
            assert not observation.spawned
            with pytest.raises(AssertionError, match="task outlived disposal"):
                observation.assert_closed()
            release.set()
            await asyncio.gather(*observation.tasks, return_exceptions=True)
            with pytest.raises(AssertionError, match="ambient cleanup failed"):
                observation.assert_closed()
        finally:
            _ACTIVATING.reset(token)
            release.set()
            await observation.emergency_cleanup()


async def test_extra_plugin_task_on_reload_is_still_rejected(tmp_path):
    package = _package(
        tmp_path,
        "import asyncio, gc\nfrom shiori_sdk.core.services import KV\n"
        "async def extra_work(): pass\n"
        "async def setup(ctx):\n"
        "    gc.collect()\n"
        "    if ctx.require(KV).increment('setups') > 1:\n"
        "        asyncio.create_task(extra_work())\n",
        "inject: [kv]\n",
    )
    callbacks_before = tuple(gc.callbacks)
    with pytest.raises(AssertionError, match="task creation order") as failure:
        await verify_contract("natural_chat", tmp_path / "workspace", directory=package)
    assert tuple(gc.callbacks) == callbacks_before
    assert "extra_work" in str(failure.value)


async def test_detached_plugin_task_failure_is_still_rejected(tmp_path):
    package = _package(
        tmp_path,
        "import asyncio\n"
        "async def failed_work():\n"
        "    raise RuntimeError('detached plugin failure')\n"
        "async def setup(ctx):\n"
        "    asyncio.create_task(failed_work())\n",
    )
    with pytest.raises(AssertionError, match="detached plugin failure"):
        await verify_contract("natural_chat", tmp_path / "workspace", directory=package)
