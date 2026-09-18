"""Desktop ZIP previews, explicit approvals, and deferred package removal."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from pathlib import Path
import re

from agent.plugin_host.package_archive import extract_package_zip
from agent.plugin_host.diagnostics import PackageContractError
from agent.plugin_host.package_fingerprint import inspect_package_content
from desktop_bridge.runtime.apply import RuntimeApplyError
from desktop_bridge.runtime.plugin_uninstall import schedule_plugin_uninstall
from desktop_bridge.runtime.plugin_package_store import (
    PackageOperation,
    PluginPackageStore,
    application_session,
    owned_child,
)

if TYPE_CHECKING:
    from desktop_bridge.runtime.plugin_management import RuntimePluginManagement


class RuntimePluginPackages:
    """Stage validated packages without executing them or changing running code."""

    def __init__(self, management: RuntimePluginManagement, workspace: Path) -> None:
        self.management = management
        self.store = PluginPackageStore(workspace)

    async def handle(
        self, method: str, payload: dict[str, Any], **apply_callbacks
    ) -> dict[str, Any]:
        """Translate filesystem and contract failures at the desktop request boundary."""
        try:
            if method == "plugins.uninstall":
                return await self.uninstall(payload, **apply_callbacks)
            handler = {
                "plugins.install.preview": self.preview,
                "plugins.install.confirm": self.confirm,
                "plugins.install.cancel": self.cancel,
            }[method]
            return handler(payload)
        except PackageContractError as exc:
            raise RuntimeApplyError(
                "plugin_package_invalid",
                exc.diagnostic.reason,
                diagnostic=exc.diagnostic.to_dict(),
            ) from exc
        except (OSError, ValueError) as exc:
            raise RuntimeApplyError(
                "plugin_package_operation_failed", str(exc)
            ) from exc

    def _records(self):
        kernel = self.management._plugin_kernel()
        if kernel is None:
            raise ValueError("插件运行时不可用")
        return kernel.inspect_candidates()

    def _target(self, plugin_id: str, candidate_id: str = ""):
        self.store.assert_available(plugin_id)
        candidates = [row for row in self._records() if row.manifest.id == plugin_id]
        if candidate_id:
            if (
                len(candidates) != 1
                or candidates[0].candidate_id != candidate_id
                or candidates[0].source != "workspace"
            ):
                raise ValueError("无法更新或卸载：插件不存在、ID 冲突或属于内置插件")
            record = candidates[0]
            if (
                owned_child(self.store.workspace / "plugins", record.plugin_dir.name)
                != record.plugin_dir.absolute()
            ):
                raise ValueError("只能管理工作区中的插件目录")
            return record
        if candidates or (self.store.workspace / "plugins" / plugin_id).exists():
            raise ValueError("插件 ID 或目录已存在；请使用该插件的更新入口")
        return None

    def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Inspect only a native-picked ZIP; bind its bytes and target to an opaque token."""
        imports = (
            self.store.workspace / "private_runtime" / "imports" / "plugin-packages"
        )
        source = Path(str(payload.get("source") or "")).absolute()
        if (
            source.parent != imports
            or source.resolve() != source
            or source.suffix.lower() != ".zip"
            or not source.is_file()
        ):
            raise ValueError("插件 ZIP 必须来自原生文件选择器")
        token, directory = self.store.create_directory()
        try:
            package = extract_package_zip(source, directory / "package")
            manifest = package.manifest
            # The external contract requires a version; legacy manual candidates
            # may still lack one, so only their display value needs normalization.
            assert manifest.version is not None
            target = self._target(manifest.id, str(payload.get("candidate_id") or ""))
            content = inspect_package_content(directory / "package")
            operation = PackageOperation(
                token=token,
                plugin_id=manifest.id,
                name=manifest.display_name or manifest.id,
                version=manifest.version,
                directory_name=target.plugin_dir.name if target else manifest.id,
                action="update" if target else "install",
                session=application_session(),
                previous_version=(target.manifest.version or "") if target else "",
                original_fingerprint=(
                    inspect_package_content(target.plugin_dir).fingerprint
                    if target
                    else ""
                ),
                staged_fingerprint=content.fingerprint,
                hashes=content.hashes,
                source_name=re.sub(
                    r"^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}-",
                    "",
                    source.name,
                    flags=re.I,
                ),
            )
            self.store.save(operation)
            return self.describe(operation)
        except BaseException:
            self.store.remove(token)
            raise
        finally:
            source.unlink(missing_ok=True)

    def describe(self, operation: PackageOperation) -> dict[str, Any]:
        """Expose the exact package identity presented in the trust dialog."""
        return {
            "token": operation.token,
            "id": operation.plugin_id,
            "name": operation.name,
            "version": operation.version,
            "previous_version": operation.previous_version,
            "action": operation.action,
            "source_name": operation.source_name,
            "directory": str(
                self.store.workspace / "plugins" / operation.directory_name
            ),
        }

    def confirm(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Require explicit trust for every preview, including every formal update."""
        operation = self.store.read(str(payload.get("token") or ""))
        if (
            payload.get("trusted") is not True
            or operation.session != application_session()
            or operation.status not in {"preview", "pending"}
        ):
            raise ValueError("请重新选择插件并明确确认完全信任")
        if operation.status == "pending":
            # A lost response may cause the user to retry this exact confirmation.
            # The persisted operation already owns its immutable content snapshot.
            return {"plugin_id": operation.plugin_id, "restart_required": True}
        self.store.assert_available(operation.plugin_id, except_token=operation.token)
        candidates = [
            row for row in self._records() if row.manifest.id == operation.plugin_id
        ]
        target = owned_child(self.store.workspace / "plugins", operation.directory_name)
        if any(
            row.source == "builtin" or row.plugin_dir.absolute() != target
            for row in candidates
        ):
            raise ValueError("插件 ID 已冲突，请取消并重新选择")
        actual = inspect_package_content(target).fingerprint if target.exists() else ""
        if (
            actual != operation.original_fingerprint
            or inspect_package_content(
                self.store.directory(operation.token) / "package"
            ).fingerprint
            != operation.staged_fingerprint
        ):
            raise ValueError("插件内容已变化，请取消并重新确认信任")
        operation.status = "pending"
        self.store.save(operation)
        self.store.clear_failures(operation.plugin_id)
        return {"plugin_id": operation.plugin_id, "restart_required": True}

    def cancel(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Discard an unapproved preview; approved operations cannot be silently cancelled."""
        operation = self.store.read(str(payload.get("token") or ""))
        if operation.status != "preview":
            raise ValueError("此插件操作已确认")
        self.store.remove(operation.token)
        return {"cancelled": True}

    async def uninstall(
        self, payload: dict[str, Any], **apply_callbacks
    ) -> dict[str, Any]:
        """Disable through the existing runtime transaction before scheduling deletion."""
        candidate_id = str(payload.get("candidate_id") or "")
        delete_data = payload.get("delete_data", False)
        if not isinstance(delete_data, bool) or not payload.get("operation_id"):
            raise ValueError("卸载需要操作 ID 和明确的数据保留选项")
        record = next(
            (row for row in self._records() if row.candidate_id == candidate_id), None
        )
        if record is None:
            raise ValueError("插件候选目录不存在")
        record = self._target(record.manifest.id, candidate_id)
        assert record is not None
        return await schedule_plugin_uninstall(
            self.management, self.store, record, payload, **apply_callbacks
        )
