"""Manual approval binds the displayed startup candidate to freshly verified content."""

from __future__ import annotations

from typing import Any

from agent.plugin_host.handle import PluginRecord
from agent.plugin_host.trust_store import PluginTrustStore
from bootstrap.app import AppRuntime
from desktop_bridge.runtime.apply import RuntimeApplyError


class RuntimePluginTrust:
    """Persist approvals without mutating or activating the current application generation."""

    def __init__(self, app: AppRuntime) -> None:
        self._app = app
        self._store = PluginTrustStore(app.workspace)

    def describe(self, record: PluginRecord) -> dict[str, Any]:
        """Expose an eligible fingerprint and pending-restart status for this exact candidate."""
        eligible = bool(
            record.source == "workspace"
            and record.fingerprint
            and record.admission
            and record.admission.code == "trust_required"
        )
        pending = (
            eligible
            and record.fingerprint is not None
            and self._store.is_trusted(record.plugin_dir, record.fingerprint)
        )
        return {
            "can_trust": eligible and not pending,
            "trust_fingerprint": record.fingerprint if eligible else None,
            "trust_directory": record.trust_directory,
            "trust_pending_restart": pending,
        }

    def confirm(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Revalidate the confirmation's directory, ID, version and full content before saving."""
        core = self._app.core
        kernel = core.plugin_manager if core is not None else None
        candidate_id, fingerprint = payload.get("candidate_id"), payload.get(
            "fingerprint"
        )
        if (
            kernel is None
            or not isinstance(candidate_id, str)
            or not isinstance(fingerprint, str)
        ):
            raise RuntimeApplyError(
                "runtime_invalid_request", "缺少插件候选目录或内容指纹"
            )
        original = next(
            (
                record
                for record in kernel.discover()
                if record.candidate_id == candidate_id
            ),
            None,
        )
        if (
            original is None
            or original.fingerprint != fingerprint
            or not self.describe(original)["trust_fingerprint"]
        ):
            raise RuntimeApplyError("plugin_not_trustable", "此插件不能授予信任")
        # Never approve new contents merely because the ID or directory still matches.
        current = [
            record
            for record in kernel.inspect_candidates()
            if record.manifest.id == original.manifest.id
        ]
        if (
            len(current) != 1
            or current[0].candidate_id != candidate_id
            or current[0].fingerprint != fingerprint
            or (
                current[0].admission is not None
                and current[0].admission.code != "trust_required"
            )
        ):
            raise RuntimeApplyError(
                "plugin_candidate_changed", "插件内容或目录已变化，请重启后重新确认信任"
            )
        try:
            self._store.approve(original.plugin_dir, fingerprint)
        except (OSError, ValueError) as exc:
            raise RuntimeApplyError(
                "plugin_trust_save_failed", f"保存插件信任失败：{exc}"
            ) from exc
        return {
            "plugin_id": original.manifest.id,
            "candidate_id": candidate_id,
            "restart_required": True,
        }
