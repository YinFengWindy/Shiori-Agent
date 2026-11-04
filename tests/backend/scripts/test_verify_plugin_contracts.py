"""Failure proofs for the production plugin lifecycle contract runner."""

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


@pytest.mark.parametrize("phase, generation", [("reload", 1), ("disable", 2)])
async def test_reported_disposal_error_cannot_pass_the_contract(
    tmp_path, phase, generation
):
    package = _package(
        tmp_path,
        "from shiori_sdk.core.services import KV\n"
        "async def setup(ctx):\n"
        "    generation = ctx.require(KV).increment('setups')\n"
        "    def close():\n"
        f"        if generation == {generation}:\n"
        f"            raise RuntimeError('{phase} disposer failed')\n"
        "    ctx.effect('contract.cleanup', close)\n",
        "inject: [kv]\n",
    )
    with pytest.raises(
        AssertionError, match=f"{phase} reported cleanup errors"
    ) as error:
        await verify_contract("natural_chat", tmp_path / "workspace", directory=package)
    assert f"{phase} disposer failed" in str(error.value)


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
