"""Pending operations do not misrepresent a running version as disabled."""

from desktop_bridge.runtime.plugin_package_listing import with_package_operations


def test_pending_update_keeps_live_activation_and_exposes_new_version(
    plugin_package_env,
):
    env = plugin_package_env
    operation = env.confirm()
    operation.action = "update"
    operation.version = "2.0.0"
    env.packages.store.save(operation)
    row = {
        "directory": str(env.target),
        "state": "ACTIVE",
        "enabled": True,
        "can_toggle": True,
        "version": "1.0.0",
    }
    [result] = with_package_operations([row], env.packages.store)
    assert result["state"] == "ACTIVE" and result["enabled"] is True
    assert result["version"] == "1.0.0" and result["pending_version"] == "2.0.0"
    assert result["pending_operation"] == "update" and not result["can_toggle"]


def test_failed_first_install_is_visible_without_claiming_an_installed_directory(
    plugin_package_env,
):
    env = plugin_package_env
    operation = env.confirm()
    operation.status = "failed"
    operation.error = "destination is locked"
    env.packages.store.save(operation)
    [row] = with_package_operations([], env.packages.store)
    assert row["state"] == "FAILED" and row["package_installed"] is False
    assert row["package_operation_error"] == "destination is locked"
    assert "pending_operation" not in row
    # The roster shape stays uniform so the renderer can group every row.
    assert row["capabilities"] == [] and row["channels"] == []
    assert row["category"] == "feature"
