"""Restart-only package publication, rollback and interrupted-operation recovery."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.discovery import discover_plugins
from agent.plugin_host.package_contract import validate_package
from agent.plugin_host.package_fingerprint import inspect_package_content
from agent.plugin_host.trust_store import PluginTrustStore
from bootstrap.paths import plugin_roots
from desktop_bridge.plugin_config_text import remove_plugin_table
from desktop_bridge.runtime.plugin_package_store import (
    PackageOperation,
    PluginPackageStore,
    application_session,
    owned_child,
    remove_owned_directory,
)
from infra.persistence.text_store import atomic_save_text

logger = logging.getLogger(__name__)


def _backup_text(directory: Path, name: str, path: Path) -> None:
    backup = directory / name
    if not backup.exists():
        atomic_save_text(
            backup,
            json.dumps(path.read_bytes().decode("utf-8") if path.exists() else None),
        )


def _restore_text(directory: Path, name: str, path: Path) -> None:
    backup = directory / name
    if backup.exists():
        text = json.loads(backup.read_text(encoding="utf-8"))
        if text is None:
            path.unlink(missing_ok=True)
        else:
            atomic_save_text(path, text)


def _check_conflicts(store: PluginPackageStore, operation: PackageOperation) -> None:
    root = store.workspace / "plugins"
    target = owned_child(root, operation.directory_name)
    records = discover_plugins(
        [*plugin_roots(), root],
        external_roots=[root],
        namespace="install",
        strict=False,
        host=None,
    )
    if any(
        record.manifest.id == operation.plugin_id
        and (record.source == "builtin" or record.plugin_dir != target)
        for record in records
    ):
        raise ValueError("插件 ID 已与其他目录或内置插件冲突")


def _publish(
    store: PluginPackageStore, operation: PackageOperation, config_path: Path
) -> None:
    directory = store.directory(operation.token)
    target = owned_child(store.workspace / "plugins", operation.directory_name)
    stage, backup = directory / "package", directory / "previous"
    data = owned_child(store.workspace / "plugin-data", operation.plugin_id)
    trust = PluginTrustStore(store.workspace)
    _check_conflicts(store, operation)
    # A target moved to previous, or staged bytes moved to target, identifies
    # an interrupted transaction. Continue it before any plugin discovery runs.
    switching = backup.exists() or (
        operation.action != "uninstall" and not stage.exists()
    )
    if not switching:
        actual = inspect_package_content(target).fingerprint if target.exists() else ""
        if actual != operation.original_fingerprint:
            raise ValueError("插件目录已变化，操作已取消；原有内容保留")
    if operation.action != "uninstall":
        candidate = target if not stage.exists() else stage
        validate_package(candidate)
        if inspect_package_content(candidate).hashes != operation.hashes:
            raise ValueError("待安装插件内容已变化，请重新选择 ZIP 并确认信任")
    elif operation.delete_data and config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        remove_plugin_table(text, operation.plugin_id)

    _backup_text(directory, "trust-before.json", trust.path)
    _backup_text(directory, "config-before.json", config_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not switching:
        target.rename(backup)
    if operation.action != "uninstall":
        if stage.exists():
            stage.rename(target)
        trust.approve(
            target,
            inspect_package_content(target).fingerprint,
            approved_session=operation.session,
        )
    else:
        trust.revoke(target)
        if operation.delete_data:
            if data.exists():
                data.rename(directory / "data-before")
            if config_path.exists():
                atomic_save_text(
                    config_path,
                    remove_plugin_table(
                        config_path.read_text(encoding="utf-8"), operation.plugin_id
                    ),
                )
    operation.status = "complete"
    store.save(operation)


def _rollback(
    store: PluginPackageStore, operation: PackageOperation, config_path: Path
) -> None:
    directory = store.directory(operation.token)
    target = owned_child(store.workspace / "plugins", operation.directory_name)
    backup = directory / "previous"
    if backup.exists():
        if target.exists():
            remove_owned_directory(target.parent, target.name)
        backup.rename(target)
    elif (
        operation.action == "install"
        and not (directory / "package").exists()
        and target.exists()
    ):
        # Only remove the exact bytes this transaction published, never a
        # conflicting package someone placed there while an install was pending.
        if inspect_package_content(target).hashes == operation.hashes:
            remove_owned_directory(target.parent, target.name)
    data_backup = directory / "data-before"
    if data_backup.exists():
        data_backup.rename(
            owned_child(store.workspace / "plugin-data", operation.plugin_id)
        )
    _restore_text(
        directory, "trust-before.json", PluginTrustStore(store.workspace).path
    )
    _restore_text(directory, "config-before.json", config_path)
    remove_owned_directory(directory, "package")


def apply_pending_plugin_operations(workspace: Path, config_path: Path) -> None:
    """Apply approved operations before config loading and plugin execution.

    A reconnect within the same desktop session leaves operations untouched.
    Startup is the error boundary: retain diagnostics and the prior package when
    a recoverable package operation fails, while allowing the host to start.
    """
    store = PluginPackageStore(workspace)
    store.remove_unjournaled_previews()
    for operation in store.list():
        if operation.status == "complete":
            store.remove(operation.token)
            continue
        if operation.session and operation.session == application_session():
            continue
        if operation.status == "preview":
            store.remove(operation.token)
            continue
        if operation.status != "pending":
            continue
        try:
            _publish(store, operation, config_path)
        except (OSError, ValueError, PackageContractError) as exc:
            _rollback(store, operation, config_path)
            operation.status = "failed"
            operation.error = str(exc)
            store.save(operation)
            logger.error(
                "插件 %s 的 %s 失败：%s", operation.plugin_id, operation.action, exc
            )
        else:
            store.remove(operation.token)
