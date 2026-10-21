"""Exact approval activates once; undecided and changed packages never execute."""

import shutil
import hashlib
import asyncio

import pytest

from agent.config import load_config_text
from bootstrap.app import AppRuntime, RuntimeFeatures
from core.roles.store import RoleStore
from desktop_bridge.runtime.service import ReloadableDesktopService
from agent.plugin_host.trust_store import PluginTrustStore
from agent.plugin_host.package_fingerprint import inspect_package_content


def _stage(workspace, plugin_id="manual", *, dependencies=(), channels=False):
    package = workspace / "plugins" / plugin_id
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        f"api: 2\npackage_contract: 1\nid: {plugin_id}\nversion: 1.0.0\n"
        "runtime_api: '>=3.1.1 <4.0.0'\nentry: backend/plugin.py\n"
        f"capabilities: [rpc{', channels' if channels else ''}]\n"
        f"dependencies: {list(dependencies)!r}\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "from pathlib import Path\n"
        "marker = Path(__file__).parents[3] / 'executed.txt'\n"
        "with marker.open('a', encoding='utf-8') as output: output.write('executed\\n')\n"
        "async def ping(payload): return {'pong': payload.get('value')}\n"
        "async def setup(ctx): ctx.rpc.register('ping', ping)\n",
        encoding="utf-8",
    )
    return package


async def _start(workspace, monkeypatch):
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda _: [workspace / "plugins"]
    )
    path = workspace / "config.toml"
    if not path.exists():
        path.write_text(
            "[llm]\nregistrations = []\n[agent.maintenance]\nmemory_optimizer_enabled = false\n",
            encoding="utf-8",
        )
    app = AppRuntime(
        load_config_text(path.read_text(encoding="utf-8")),
        workspace,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    return app, ReloadableDesktopService(app, path, RoleStore(workspace))


async def _request(service, method, payload=None):
    return await service.handle(
        {"id": method, "method": method, "payload": payload or {}},
        emit_event=lambda _: None,
    )


@pytest.mark.asyncio
async def test_trust_activates_now_and_changed_backend_cannot_reload(
    tmp_path, monkeypatch
):
    package = _stage(tmp_path)
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        assert row["state"] == "UNTRUSTED" and row["can_trust"]
        assert not (tmp_path / "executed.txt").exists()
        generation = app.generation
        result = await _request(
            service,
            "plugins.trust",
            {
                "candidate_id": row["candidate_id"],
                "fingerprint": row["trust_fingerprint"],
            },
        )
        assert result.error is None and not result.payload["restart_required"]
        assert app.generation == generation
        assert (tmp_path / "executed.txt").read_text(encoding="utf-8") == "executed\n"
        [active] = (await _request(service, "plugins.list")).payload["plugins"]
        assert active["state"] == "ACTIVE"
        assert not active["can_trust"] and not active["trust_pending_restart"]
        assert (
            active["content_hashes"]["backend/plugin.py"]
            == hashlib.sha256((package / "backend/plugin.py").read_bytes()).hexdigest()
        )
        assert (
            await _request(service, "plugin.manual.ping", {"value": 7})
        ).payload == {"pong": 7}
        source = package / "backend/plugin.py"
        source.write_text(
            source.read_text(encoding="utf-8")
            + "\nraise RuntimeError('must not execute new code')\n",
            encoding="utf-8",
        )
        for index, enabled in enumerate((False, True)):
            changed = await _request(
                service,
                "plugins.setEnabled",
                {
                    "plugin_id": "manual",
                    "enabled": enabled,
                    "operation_id": f"toggle-{index}",
                },
            )
            assert changed.error is None
        [changed] = (await _request(service, "plugins.list")).payload["plugins"]
        assert changed["state"] == "UNTRUSTED"
        assert "must not execute" not in changed["error"]
        assert (await _request(service, "plugin.manual.ping")).error is not None
    finally:
        await service.aclose()
        await app.shutdown()
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [changed] = (await _request(service, "plugins.list")).payload["plugins"]
        assert changed["state"] == "UNTRUSTED" and changed["can_trust"]
        assert changed["trust_fingerprint"] != row["trust_fingerprint"]
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["content", "conflict", "directory"])
async def test_confirmation_rejects_changed_or_replaced_displayed_candidate(
    tmp_path, monkeypatch, change
):
    package = _stage(tmp_path)
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        if change == "content":
            (package / "asset.txt").write_text("added since review", encoding="utf-8")
        elif change == "conflict":
            shutil.copytree(package, package.with_name("duplicate"))
        else:
            package.rename(package.with_name("moved"))
        result = await _request(
            service,
            "plugins.trust",
            {
                "candidate_id": row["candidate_id"],
                "fingerprint": row["trust_fingerprint"],
            },
        )
        assert result.error.code == "plugin_candidate_changed"
        assert not (tmp_path / "private_runtime/plugin-trust.json").exists()
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_trust_preserves_disabled_preference(tmp_path, monkeypatch):
    _stage(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[llm]\nregistrations = []\n[plugins.manual]\nenabled = false\n",
        encoding="utf-8",
    )
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        result = await _request(
            service,
            "plugins.trust",
            {
                "candidate_id": row["candidate_id"],
                "fingerprint": row["trust_fingerprint"],
            },
        )
        assert result.error is None
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        assert row["state"] == "DISABLED" and row["enabled"] is False
        assert not (tmp_path / "executed.txt").exists()
    finally:
        await service.aclose()
        await app.shutdown()
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        assert row["state"] == "DISABLED" and row["enabled"] is False
        assert row["can_toggle"] and not row["can_trust"]
    finally:
        await service.aclose()
        await app.shutdown()


async def _approve(service, row, *, enable=False, operation_id=""):
    return await _request(
        service,
        "plugins.trust",
        {
            "candidate_id": row["candidate_id"],
            "fingerprint": row["trust_fingerprint"],
            "enable": enable,
            "operation_id": operation_id,
        },
    )


@pytest.mark.asyncio
async def test_explicit_enable_and_duplicate_confirmation_execute_once(
    tmp_path, monkeypatch
):
    _stage(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[llm]\nregistrations = []\n[plugins.manual]\nenabled = false\n",
        encoding="utf-8",
    )
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        results = await asyncio.gather(
            *(
                _approve(service, row, enable=True, operation_id="one-confirmation")
                for _ in range(2)
            )
        )
        assert all(result.error is None for result in results)
        assert (tmp_path / "executed.txt").read_text(encoding="utf-8") == "executed\n"
        assert (
            await _request(service, "plugin.manual.ping", {"value": 12})
        ).payload == {"pong": 12}
        assert app.config.plugins["manual"]["enabled"] is True
        conflict = await _approve(service, row, operation_id="one-confirmation")
        assert conflict.error.code == "runtime_operation_conflict"
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_channel_admission_swaps_generation_without_discovering_new_packages(
    tmp_path, monkeypatch
):
    _stage(tmp_path, channels=True)
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        _stage(tmp_path, "late_package")
        generation = app.generation
        result = await _approve(service, row)
        assert result.error is None
        assert app.generation == generation + 1
        [current] = (await _request(service, "plugins.list")).payload["plugins"]
        assert current["id"] == "manual" and current["state"] == "ACTIVE"
        assert (
            await _request(service, "plugin.manual.ping", {"value": 5})
        ).payload == {"pong": 5}
        assert (await _request(service, "plugin.late_package.ping")).error is not None
        assert (tmp_path / "executed.txt").read_text(encoding="utf-8") == "executed\n"
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_dependencies_become_trustable_but_are_not_implicitly_approved(
    tmp_path, monkeypatch
):
    _stage(tmp_path, "consumer", dependencies=("provider",))
    _stage(tmp_path, "provider")
    app, service = await _start(tmp_path, monkeypatch)
    try:
        rows = (await _request(service, "plugins.list")).payload["plugins"]
        consumer, provider = sorted(rows, key=lambda row: row["id"])
        assert consumer["state"] == "BLOCKED" and not consumer["can_trust"]
        assert (await _approve(service, provider)).error is None
        rows = (await _request(service, "plugins.list")).payload["plugins"]
        consumer, provider = sorted(rows, key=lambda row: row["id"])
        assert provider["state"] == "ACTIVE"
        assert consumer["state"] == "UNTRUSTED" and consumer["can_trust"]
        assert (await _request(service, "plugin.consumer.ping")).error is not None
        assert (tmp_path / "executed.txt").read_text(encoding="utf-8") == "executed\n"
        assert (await _approve(service, consumer)).error is None
        assert (
            await _request(service, "plugin.consumer.ping", {"value": 4})
        ).payload == {"pong": 4}
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_state", ["disabled", "failed"])
async def test_unrelated_trust_preserves_runtime_dependency_failures(
    tmp_path, monkeypatch, provider_state
):
    provider = _stage(tmp_path, "provider")
    consumer = _stage(tmp_path, "consumer", dependencies=("provider",))
    if provider_state == "failed":
        source = provider / "backend/plugin.py"
        source.write_text(
            source.read_text(encoding="utf-8")
            + "\nraise RuntimeError('provider failed')\n",
            encoding="utf-8",
        )
    for package in (provider, consumer):
        PluginTrustStore(tmp_path).approve(
            package, inspect_package_content(package).fingerprint, approved_session=""
        )
    _stage(tmp_path, "unrelated")
    (tmp_path / "config.toml").write_text(
        "[llm]\nregistrations = []\n[plugins.provider]\n"
        f"enabled = {'false' if provider_state == 'disabled' else 'true'}\n",
        encoding="utf-8",
    )
    app, service = await _start(tmp_path, monkeypatch)
    try:
        before = {
            row["id"]: row
            for row in (await _request(service, "plugins.list")).payload["plugins"]
        }
        assert before["consumer"]["state"] == "BLOCKED"
        assert before["consumer"]["diagnostic"]["code"] == "dependency_unavailable"
        assert before["provider"]["state"] == provider_state.upper()
        assert (await _approve(service, before["unrelated"])).error is None
        after = {
            row["id"]: row
            for row in (await _request(service, "plugins.list")).payload["plugins"]
        }
        for plugin_id in ("consumer", "provider"):
            for field in ("enabled", "state", "error", "diagnostic"):
                assert after[plugin_id][field] == before[plugin_id][field]
        assert (await _request(service, "plugin.consumer.ping")).error is not None
        assert (
            await _request(service, "plugin.unrelated.ping", {"value": 19})
        ).payload == {"pong": 19}
        if provider_state == "disabled":
            enabled = await _request(
                service,
                "plugins.setEnabled",
                {
                    "plugin_id": "provider",
                    "enabled": True,
                    "operation_id": "enable-provider",
                },
            )
            assert enabled.error is None
            assert (
                await _request(service, "plugin.consumer.ping", {"value": 23})
            ).payload == {"pong": 23}
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("channels", [False, True])
async def test_pretrusted_enabled_consumer_recovers_when_provider_is_approved(
    tmp_path, monkeypatch, channels
):
    consumer = _stage(tmp_path, "consumer", dependencies=("provider",))
    disabled = _stage(tmp_path, "disabled_consumer", dependencies=("provider",))
    for package in (consumer, disabled):
        PluginTrustStore(tmp_path).approve(
            package, inspect_package_content(package).fingerprint, approved_session=""
        )
    _stage(tmp_path, "provider", channels=channels)
    _stage(tmp_path, "untrusted_consumer", dependencies=("provider",))
    (tmp_path / "config.toml").write_text(
        "[llm]\nregistrations = []\n[plugins.disabled_consumer]\nenabled = false\n",
        encoding="utf-8",
    )
    app, service = await _start(tmp_path, monkeypatch)
    try:
        before = {
            row["id"]: row
            for row in (await _request(service, "plugins.list")).payload["plugins"]
        }
        assert before["consumer"]["state"] == "BLOCKED"
        assert before["consumer"]["trusted"]
        assert (await _approve(service, before["provider"])).error is None
        after = {
            row["id"]: row
            for row in (await _request(service, "plugins.list")).payload["plugins"]
        }
        assert after["provider"]["state"] == "ACTIVE"
        assert after["consumer"]["state"] == "ACTIVE"
        assert (
            await _request(service, "plugin.consumer.ping", {"value": 29})
        ).payload == {"pong": 29}
        assert after["disabled_consumer"]["state"] == "DISABLED"
        assert not after["disabled_consumer"]["enabled"]
        assert after["untrusted_consumer"]["state"] == "UNTRUSTED"
        assert not after["untrusted_consumer"]["trusted"]
        assert after["untrusted_consumer"]["can_trust"]
        assert (
            await _request(service, "plugin.disabled_consumer.ping")
        ).error is not None
        assert (
            await _request(service, "plugin.untrusted_consumer.ping")
        ).error is not None
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_bridge_restart_cannot_run_replaced_code_in_the_same_desktop_session(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "desktop-one")
    package = _stage(tmp_path)
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        assert (await _approve(service, row)).error is None
    finally:
        await service.aclose()
        await app.shutdown()
    source = package / "backend/plugin.py"
    source.write_text(
        source.read_text(encoding="utf-8").replace("'pong'", "'new_pong'"),
        encoding="utf-8",
    )
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        assert row["state"] == "RESTART_REQUIRED" and not row["can_trust"]
        assert (tmp_path / "executed.txt").read_text(encoding="utf-8") == "executed\n"
    finally:
        await service.aclose()
        await app.shutdown()
    monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "desktop-two")
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        assert row["state"] == "UNTRUSTED" and row["can_trust"]
        assert (await _approve(service, row)).error is None
        assert (
            await _request(service, "plugin.manual.ping", {"value": 8})
        ).payload == {"new_pong": 8}
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_failed_activation_keeps_trust_and_reports_actual_failure(
    tmp_path, monkeypatch
):
    package = _stage(tmp_path)
    source = package / "backend/plugin.py"
    source.write_text(
        source.read_text(encoding="utf-8")
        + "\nraise RuntimeError('setup marker failure')\n",
        encoding="utf-8",
    )
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        result = await _approve(service, row)
        assert result.error is None and result.payload["state"] == "FAILED"
        assert "setup marker failure" in result.payload["error"]
        [current] = (await _request(service, "plugins.list")).payload["plugins"]
        assert not current["can_trust"] and current["can_toggle"]
        assert (await _request(service, "health")).error is None
        assert (await _request(service, "plugin.manual.ping")).error is not None
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_refused_generation_activation_reports_restart_without_stopping_other_plugins(
    tmp_path, monkeypatch
):
    unsafe = _stage(tmp_path, "unsafe")
    manifest = unsafe / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "supports_hot_unload: false\n",
        encoding="utf-8",
    )
    PluginTrustStore(tmp_path).approve(
        unsafe, inspect_package_content(unsafe).fingerprint, approved_session=""
    )
    _stage(tmp_path, channels=True)
    app, service = await _start(tmp_path, monkeypatch)
    try:
        rows = (await _request(service, "plugins.list")).payload["plugins"]
        row = next(row for row in rows if row["id"] == "manual")
        result = await _approve(service, row)
        assert result.error.code == "plugin_restart_required"
        rows = (await _request(service, "plugins.list")).payload["plugins"]
        current = next(row for row in rows if row["id"] == "manual")
        assert current["trusted"] and current["state"] == "RESTART_REQUIRED"
        assert not current["can_toggle"] and not current["can_trust"]
        assert (
            await _request(service, "plugin.unsafe.ping", {"value": 6})
        ).payload == {"pong": 6}
        assert (tmp_path / "executed.txt").read_text(encoding="utf-8") == "executed\n"
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_caller_cancellation_after_approval_cannot_leave_activation_half_applied(
    tmp_path, monkeypatch
):
    _stage(tmp_path)
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        kernel = app.core.plugin_manager
        original = kernel.admit_trusted_candidate
        started, release = asyncio.Event(), asyncio.Event()

        async def delayed(candidate):
            started.set()
            await release.wait()
            await original(candidate)

        monkeypatch.setattr(kernel, "admit_trusted_candidate", delayed)
        request = asyncio.create_task(
            _approve(service, row, operation_id="cancelled-confirmation")
        )
        await started.wait()
        request.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await request
        [current] = (await _request(service, "plugins.list")).payload["plugins"]
        assert current["state"] == "ACTIVE" and current["trusted"]
        assert (
            await _request(service, "plugin.manual.ping", {"value": 3})
        ).payload == {"pong": 3}
        assert (tmp_path / "executed.txt").read_text(encoding="utf-8") == "executed\n"
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_enable_intent_from_an_older_dialog_still_uses_normal_hot_enable(
    tmp_path, monkeypatch
):
    _stage(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[llm]\nregistrations = []\n[plugins.manual]\nenabled = false\n",
        encoding="utf-8",
    )
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        generation = app.generation
        assert (await _approve(service, row)).error is None
        assert not (tmp_path / "executed.txt").exists()
        assert (await _approve(service, row, enable=True)).error is None
        assert app.generation == generation
        assert (
            await _request(service, "plugin.manual.ping", {"value": 11})
        ).payload == {"pong": 11}
    finally:
        await service.aclose()
        await app.shutdown()
