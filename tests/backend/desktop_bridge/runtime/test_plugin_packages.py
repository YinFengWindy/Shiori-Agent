"""Explicit package confirmation cannot silently overwrite or trust changed bytes."""

import shutil

import pytest

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.package_archive import extract_package_zip
from desktop_bridge.runtime.apply import RuntimeApplyError


def test_cancel_removes_preview_without_installing_or_trusting(plugin_package_env):
    env = plugin_package_env
    preview = env.preview()
    assert preview["action"] == "install"
    assert not env.target.exists()
    assert not (env.workspace / "private_runtime/plugin-trust.json").exists()
    env.packages.cancel({"token": preview["token"]})
    assert env.packages.store.list() == []
    assert list(env.packages.store.root.iterdir()) == []


def test_retrying_confirmation_after_lost_response_is_idempotent(plugin_package_env):
    env = plugin_package_env
    operation = env.confirm()
    result = env.packages.confirm({"token": operation.token, "trusted": True})
    assert result["restart_required"] is True
    assert len(env.packages.store.list()) == 1
    assert not env.target.exists()


def test_preview_shows_original_zip_name_without_native_staging_prefix(
    plugin_package_env,
):
    env = plugin_package_env
    source = env.archive()
    staged = source.with_name("b397883e-7d88-4c5c-8cdd-351c27cdd69b-" + source.name)
    source.rename(staged)
    result = env.packages.preview({"source": str(staged)})
    assert result["source_name"] == source.name


@pytest.mark.parametrize("change", ["no-confirmation", "staging", "target", "conflict"])
def test_confirmation_rejects_missing_trust_and_changed_snapshots(
    plugin_package_env, change
):
    env = plugin_package_env
    preview = env.preview()
    token = preview["token"]
    if change == "staging":
        (env.packages.store.directory(token) / "package/backend/plugin.py").write_text(
            "raise RuntimeError('changed')", encoding="utf-8"
        )
    elif change == "target":
        extract_package_zip(env.archive(), env.target)
    elif change == "conflict":
        extract_package_zip(env.archive(), env.workspace / "plugins/duplicate")
    with pytest.raises(ValueError):
        env.packages.confirm({"token": token, "trusted": change != "no-confirmation"})
    assert env.packages.store.read(token).status == "preview"
    assert not (env.workspace / "private_runtime/plugin-trust.json").exists()


@pytest.mark.parametrize("conflict", ["builtin", "duplicate", "existing", "wrong-id"])
def test_install_update_rejects_ambiguous_targets(plugin_package_env, conflict):
    env = plugin_package_env
    root = env.builtins / "demo" if conflict == "builtin" else env.target
    extract_package_zip(env.archive(), root)
    if conflict == "duplicate":
        shutil.copytree(root, env.workspace / "plugins/duplicate")
    candidate = "" if conflict == "existing" else str(root)
    with pytest.raises(ValueError):
        env.preview(
            candidate_id=candidate,
            plugin_id="other" if conflict == "wrong-id" else "demo",
        )
    assert list(env.packages.store.root.iterdir()) == []
    assert (root / "manifest.yaml").exists()


def test_invalid_archive_leaves_no_partial_package(plugin_package_env):
    env = plugin_package_env
    with pytest.raises(PackageContractError):
        env.preview(invalid=True)
    assert not env.target.exists()
    assert list(env.packages.store.root.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("unsafe", [False, True])
async def test_uninstall_uses_existing_hot_disable_and_defers_unsafe_unload(
    plugin_package_env, unsafe
):
    env = plugin_package_env
    extract_package_zip(env.archive(), env.target)
    if unsafe:
        env.management.set_enabled.side_effect = RuntimeApplyError(
            "plugin_restart_required", "needs restart"
        )
    result = await env.packages.uninstall(
        {
            "candidate_id": str(env.target),
            "delete_data": False,
            "operation_id": "remove",
        }
    )
    assert result["restart_required"]
    env.management.set_enabled.assert_awaited_once()
    assert env.management.set_enabled.call_args.args[0]["enabled"] is False
    assert env.target.exists()
    [operation] = env.packages.store.list()
    assert operation.status == "pending" and operation.action == "uninstall"
    assert not operation.delete_data


@pytest.mark.asyncio
async def test_uninstall_does_not_queue_after_failed_resource_cleanup(
    plugin_package_env,
):
    env = plugin_package_env
    extract_package_zip(env.archive(), env.target)
    env.management.set_enabled.side_effect = RuntimeApplyError(
        "runtime_apply_failed", "cleanup failed"
    )
    with pytest.raises(RuntimeApplyError, match="cleanup failed"):
        await env.packages.uninstall(
            {"candidate_id": str(env.target), "operation_id": "remove"}
        )
    assert env.packages.store.list() == []
    assert env.target.exists()
