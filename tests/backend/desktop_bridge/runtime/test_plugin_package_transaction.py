"""Disk publication survives failure/restart without replacing live plugin bytes."""

from pathlib import Path
import shutil
import tomllib

import pytest

from agent.plugin_host.package_fingerprint import inspect_package_content
from agent.plugin_host.trust_store import PluginTrustStore
from desktop_bridge.runtime.plugin_package_transaction import (
    apply_pending_plugin_operations,
)


def _restart(env, monkeypatch, session):
    monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", session)
    apply_pending_plugin_operations(env.workspace, env.config)


def test_restart_reclaims_extraction_interrupted_before_preview_journal(
    plugin_package_env,
):
    env = plugin_package_env
    _, directory = env.packages.store.create_directory()
    package = directory / "package"
    package.mkdir()
    (package / "partial.py").write_text("unfinished", encoding="utf-8")
    apply_pending_plugin_operations(env.workspace, env.config)
    assert not directory.exists()
    assert not env.target.exists()


def test_application_restart_publishes_install_but_bridge_reconnect_does_not(
    plugin_package_env, monkeypatch
):
    env = plugin_package_env
    env.confirm()
    apply_pending_plugin_operations(env.workspace, env.config)
    assert not env.target.exists()
    assert len(env.packages.store.list()) == 1
    _restart(env, monkeypatch, "session-b")
    content = inspect_package_content(env.target)
    assert PluginTrustStore(env.workspace).is_trusted(
        env.target, content.fingerprint, activation=True
    )
    assert env.packages.store.list() == []
    assert (
        tomllib.loads(env.config.read_text(encoding="utf-8"))["plugins"]["demo"][
            "enabled"
        ]
        is False
    )


def test_update_preserves_old_code_until_restart_and_keeps_disabled_configuration(
    plugin_package_env, monkeypatch
):
    env = plugin_package_env
    env.confirm()
    _restart(env, monkeypatch, "session-b")
    old = inspect_package_content(env.target).fingerprint
    env.confirm("2.0.0", str(env.target))
    assert inspect_package_content(env.target).fingerprint == old
    _restart(env, monkeypatch, "session-c")
    assert "VERSION = '2.0.0'" in (env.target / "backend/plugin.py").read_text(
        encoding="utf-8"
    )
    assert inspect_package_content(env.target).fingerprint != old
    assert tomllib.loads(env.config.read_text(encoding="utf-8"))["plugins"]["demo"] == {
        "enabled": False,
        "note": "keep",
    }


@pytest.mark.parametrize("failure", ["rename", "trust", "stage-changed", "conflict"])
def test_update_failure_keeps_old_package_and_approval(
    plugin_package_env, monkeypatch, failure
):
    env = plugin_package_env
    env.confirm()
    _restart(env, monkeypatch, "session-b")
    original = inspect_package_content(env.target).fingerprint
    trust_file = PluginTrustStore(env.workspace).path
    old_trust = trust_file.read_bytes()
    operation = env.confirm("2.0.0", str(env.target))
    stage = env.packages.store.directory(operation.token) / "package"
    if failure == "rename":
        rename = Path.rename

        def fail_publish(path, target):
            if path == stage:
                raise OSError("publish denied")
            return rename(path, target)

        monkeypatch.setattr(Path, "rename", fail_publish)
    elif failure == "trust":
        monkeypatch.setattr(
            PluginTrustStore,
            "approve",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("trust denied")),
        )
    elif failure == "stage-changed":
        (stage / "backend/plugin.py").write_text("changed", encoding="utf-8")
    else:
        shutil.copytree(env.target, env.builtins / "conflicting")
    _restart(env, monkeypatch, "session-c")
    assert inspect_package_content(env.target).fingerprint == original
    assert trust_file.read_bytes() == old_trust
    [failed] = env.packages.store.list()
    assert failed.status == "failed" and failed.error
    assert not stage.exists()
    assert not (stage.parent / "previous").exists()


@pytest.mark.parametrize(
    "point", ["before-new-directory", "after-new-directory", "after-new-trust"]
)
def test_interrupted_update_recovers_before_execution(
    plugin_package_env, monkeypatch, point
):
    env = plugin_package_env
    env.confirm()
    _restart(env, monkeypatch, "session-b")
    operation = env.confirm("2.0.0", str(env.target))
    directory = env.packages.store.directory(operation.token)
    env.target.rename(directory / "previous")
    if point != "before-new-directory":
        (directory / "package").rename(env.target)
    if point == "after-new-trust":
        PluginTrustStore(env.workspace).approve(
            env.target,
            inspect_package_content(env.target).fingerprint,
            approved_session=operation.session,
        )
    _restart(env, monkeypatch, "session-c")
    content = inspect_package_content(env.target)
    assert "VERSION = '2.0.0'" in (env.target / "backend/plugin.py").read_text(
        encoding="utf-8"
    )
    assert PluginTrustStore(env.workspace).is_trusted(
        env.target, content.fingerprint, activation=True
    )
    assert env.packages.store.list() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_data", [False, True])
async def test_uninstall_revokes_trust_and_honors_data_choice(
    plugin_package_env, monkeypatch, delete_data
):
    env = plugin_package_env
    env.confirm()
    _restart(env, monkeypatch, "session-b")
    fingerprint = inspect_package_content(env.target).fingerprint
    data = env.workspace / "plugin-data/demo"
    data.mkdir(parents=True)
    (data / "kv.json").write_text('{"note":"keep"}', encoding="utf-8")
    await env.packages.uninstall(
        {
            "candidate_id": str(env.target),
            "delete_data": delete_data,
            "operation_id": "remove",
        }
    )
    assert env.target.exists() and data.exists()
    _restart(env, monkeypatch, "session-c")
    assert not env.target.exists()
    assert not PluginTrustStore(env.workspace).is_trusted(env.target, fingerprint)
    assert data.exists() is not delete_data
    assert (
        "demo"
        in tomllib.loads(env.config.read_text(encoding="utf-8")).get("plugins", {})
    ) is not delete_data
    env.confirm()
    _restart(env, monkeypatch, "session-d")
    assert env.target.exists()
    assert data.exists() is not delete_data


@pytest.mark.asyncio
async def test_failed_data_deletion_restores_code_data_config_and_trust(
    plugin_package_env, monkeypatch
):
    env = plugin_package_env
    env.confirm()
    _restart(env, monkeypatch, "session-b")
    data = env.workspace / "plugin-data/demo"
    data.mkdir(parents=True)
    (data / "kv.json").write_text("{}", encoding="utf-8")
    old_trust = PluginTrustStore(env.workspace).path.read_bytes()
    old_config = env.config.read_bytes()
    await env.packages.uninstall(
        {"candidate_id": str(env.target), "delete_data": True, "operation_id": "remove"}
    )
    rename = Path.rename

    def fail_data(path, target):
        if path == data:
            raise OSError("data locked")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_data)
    _restart(env, monkeypatch, "session-c")
    assert env.target.exists() and (data / "kv.json").exists()
    assert env.config.read_bytes() == old_config
    assert PluginTrustStore(env.workspace).path.read_bytes() == old_trust
