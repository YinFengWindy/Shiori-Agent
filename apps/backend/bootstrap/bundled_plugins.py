"""Install shipped voice packages once, retaining independent updates and removals."""

from pathlib import Path
from typing import Any

from agent.plugin_host.package_fingerprint import inspect_package_content
from agent.plugin_host.trust_store import PluginTrustStore
from bootstrap.bundled_plugin_files import remove_bundled_stage, stage_bundled_plugin
from bootstrap.plugin_distribution import bundled_plugin_sources
from shiori_sdk.files.json import atomic_save_json, load_json


def ensure_bundled_plugins(workspace: Path) -> None:
    """Publish trusted distribution copies without touching existing user packages.

    Completed receipts survive uninstall and plugin-data deletion. A pending
    receipt owns only its exact staged bytes; restart can finish a publication
    interrupted between directory rename, trust persistence and receipt commit.
    """
    workspace = workspace.absolute()
    for plugin_id, source in bundled_plugin_sources().items():
        _ensure_one(workspace, plugin_id, source)


def _ensure_one(workspace: Path, plugin_id: str, source: Path) -> None:
    from desktop_bridge.runtime.plugin_package_store import owned_child

    owner = owned_child(
        workspace / "private_runtime" / "bundled-plugin-seeds", plugin_id
    )
    receipt_path = owned_child(owner, "receipt.json")
    stage = owned_child(owner, "package")
    target = owned_child(workspace / "plugins", plugin_id)
    receipt = _read_receipt(receipt_path)
    if receipt is not None and receipt["state"] == "complete":
        return
    if receipt is None:
        if target.exists() or target.is_symlink():
            # A matching name grants no trust. Leave discovery to report an
            # existing package's trust, contract or conflict state normally.
            atomic_save_json(receipt_path, {"version": 1, "state": "complete"})
            return
        remove_bundled_stage(stage, workspace)
        hashes = stage_bundled_plugin(source, stage, plugin_id)
        receipt = {"version": 1, "state": "pending", "hashes": hashes}
        atomic_save_json(receipt_path, receipt)
    hashes = receipt["hashes"]
    if not target.exists() and not target.is_symlink():
        if not stage.exists() or inspect_package_content(stage).hashes != hashes:
            raise ValueError(f"随包插件暂存内容损坏: {plugin_id}")
        target.parent.mkdir(parents=True, exist_ok=True)
        stage.rename(target)
    # Only a copy owned by this pending journal can inherit distribution trust.
    # Changed or pre-existing bytes are never overwritten or approved.
    content = inspect_package_content(target)
    if content.hashes == hashes:
        PluginTrustStore(workspace).approve(
            target, content.fingerprint, approved_session=""
        )
    atomic_save_json(receipt_path, {"version": 1, "state": "complete"})
    remove_bundled_stage(stage, workspace)


def _read_receipt(path: Path) -> dict[str, Any] | None:
    receipt = load_json(path)
    if receipt is None:
        return None
    if (
        not isinstance(receipt, dict)
        or receipt.get("version") != 1
        or receipt.get("state") not in {"pending", "complete"}
    ):
        raise ValueError("随包插件安装回执无效")
    if receipt["state"] == "pending":
        hashes = receipt.get("hashes")
        if (
            not isinstance(hashes, dict)
            or not hashes
            or any(
                not isinstance(name, str) or not isinstance(digest, str)
                for name, digest in hashes.items()
            )
        ):
            raise ValueError("随包插件安装回执缺少内容标识")
    return receipt
