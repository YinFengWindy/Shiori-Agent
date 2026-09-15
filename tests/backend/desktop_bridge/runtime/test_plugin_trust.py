"""Explicit approval never executes code until a fresh application startup."""

import shutil
import hashlib

import pytest

from agent.config import load_config_text
from bootstrap.app import AppRuntime, RuntimeFeatures
from core.roles.store import RoleStore
from desktop_bridge.runtime.service import ReloadableDesktopService


def _stage(workspace):
    package = workspace / "plugins" / "manual"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\npackage_contract: 1\nid: manual\nversion: 1.0.0\n"
        "runtime_api: '>=2.0.0 <3.0.0'\nentry: backend/plugin.py\ncapabilities: [rpc]\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
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
async def test_trust_waits_for_restart_and_changed_backend_cannot_reload(
    tmp_path, monkeypatch
):
    package = _stage(tmp_path)
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [row] = (await _request(service, "plugins.list")).payload["plugins"]
        assert row["state"] == "UNTRUSTED" and row["can_trust"]
        result = await _request(
            service,
            "plugins.trust",
            {
                "candidate_id": row["candidate_id"],
                "fingerprint": row["trust_fingerprint"],
            },
        )
        assert result.error is None and result.payload["restart_required"]
        [pending] = (await _request(service, "plugins.list")).payload["plugins"]
        assert pending["trust_pending_restart"] and not pending["can_toggle"]
        assert pending["state"] == "UNTRUSTED"
        assert (await _request(service, "plugin.manual.ping")).error is not None
    finally:
        await service.aclose()
        await app.shutdown()
    app, service = await _start(tmp_path, monkeypatch)
    try:
        [active] = (await _request(service, "plugins.list")).payload["plugins"]
        assert active["state"] == "ACTIVE"
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
