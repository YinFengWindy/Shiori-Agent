"""Explicit content approval and first activation share the settings operation lock."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

from agent.plugin_host.handle import PluginRecord
from agent.plugin_host.kernel import plugin_enabled
from agent.plugin_host.trust_store import PluginTrustStore
from bootstrap.app import AppRuntime
from core.common.cancellation import finish_started
from desktop_bridge.plugin_config_text import merge_plugin_table
from desktop_bridge.runtime.apply import (
    DerivedWrite,
    RuntimeApplyError,
    RuntimeSettingsApplication,
    assert_plugin_table_isolated,
    read_plugin_table,
)


class RuntimePluginTrust:
    """Approve one displayed candidate without admitting undisplayed packages."""

    def __init__(self, app: AppRuntime, settings: RuntimeSettingsApplication) -> None:
        self._app = app
        self._settings = settings
        self._store = PluginTrustStore(app.workspace)

    def describe(self, record: PluginRecord) -> dict[str, Any]:
        """Expose the exact candidate still awaiting approval or a safe retry."""
        eligible = bool(
            record.source == "workspace"
            and record.fingerprint
            and record.admission
            and record.admission.code == "trust_required"
        )
        return {
            "can_trust": eligible,
            "trusted": record.source == "builtin"
            or bool(
                record.fingerprint
                and self._store.is_trusted(
                    record.plugin_dir, record.fingerprint, activation=True
                )
            ),
            "trust_fingerprint": record.fingerprint if eligible else None,
            "trust_directory": record.trust_directory,
            "trust_pending_restart": False,
        }

    def _candidate(self, candidate_id: str, fingerprint: str) -> PluginRecord:
        kernel = self._app.core.plugin_manager if self._app.core is not None else None
        original = (
            next(
                (
                    record
                    for record in kernel.discover()
                    if record.candidate_id == candidate_id
                ),
                None,
            )
            if kernel is not None
            else None
        )
        if (
            original is None
            or original.source != "workspace"
            or original.fingerprint != fingerprint
        ):
            raise RuntimeApplyError(
                "plugin_not_trustable", "此插件候选已变化，请重新读取"
            )
        return original

    async def _admit(self, candidate_id: str, fingerprint: str) -> str | None:
        original = self._candidate(candidate_id, fingerprint)
        kernel = self._app.core.plugin_manager if self._app.core is not None else None
        assert kernel is not None
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
                "plugin_candidate_changed",
                "插件内容、目录或运行状态已变化，请重新读取后确认",
            )
        if original.admission is None:
            # A duplicate confirmation cannot rerun an already admitted plugin.
            if self._store.is_trusted(
                original.plugin_dir, fingerprint, activation=True
            ):
                return None
            raise RuntimeApplyError(
                "plugin_not_trustable", "插件授权已变化，请重启后确认"
            )
        if original.admission.code != "trust_required":
            raise RuntimeApplyError("plugin_not_trustable", "此插件不能授予信任")
        try:
            # Immediate approval is explicit. Already executed code remains frozen
            # by PluginExecutionIdentity, including across bridge reconnects.
            self._store.approve(original.plugin_dir, fingerprint, approved_session="")
        except (OSError, ValueError) as exc:
            raise RuntimeApplyError(
                "plugin_trust_save_failed", f"保存插件信任失败：{exc}"
            ) from exc
        await kernel.admit_trusted_candidate(replace(current[0], admission=None))
        return original.manifest.id

    async def confirm(
        self, payload: dict[str, Any], *, prepare_service, publish_service
    ) -> dict[str, Any]:
        """Approve exact bytes and optionally enable; trust-only preserves disabled state."""
        candidate_id, fingerprint = payload.get("candidate_id"), payload.get(
            "fingerprint"
        )
        enable = payload.get("enable", False)
        if (
            not isinstance(candidate_id, str)
            or not isinstance(fingerprint, str)
            or type(enable) is not bool
        ):
            raise RuntimeApplyError(
                "runtime_invalid_request", "缺少插件候选目录或内容指纹"
            )

        def derive(text: str) -> str:
            original = self._candidate(candidate_id, fingerprint)
            if not enable:
                return text
            plugin_id = original.manifest.id
            values = read_plugin_table(text, plugin_id)
            values["enabled"] = True
            updated = merge_plugin_table(text, plugin_id, values)
            assert_plugin_table_isolated(plugin_id, text, updated)
            return updated

        operation_id = payload.get("operation_id") or uuid4().hex
        admitted_plugin: str | None = None
        activation_requested = False

        async def prepare_admission() -> str | None:
            nonlocal admitted_plugin, activation_requested
            original = self._candidate(candidate_id, fingerprint)
            activation_requested = enable or plugin_enabled(
                original.manifest,
                self._app.config.plugins.get(original.manifest.id, {}),
            )
            admitted_plugin = await self._admit(candidate_id, fingerprint)
            return admitted_plugin

        try:
            result = await finish_started(
                self._settings.apply(
                    {"operation_id": operation_id},
                    prepare_service=prepare_service,
                    publish_service=publish_service,
                    derive=DerivedWrite(
                        build_config_toml=derive,
                        fingerprint_payload={
                            "trust": candidate_id,
                            "fingerprint": fingerprint,
                            "enable": enable,
                        },
                        reload_plugin=self._candidate(
                            candidate_id, fingerprint
                        ).manifest.id,
                        toggle=True,
                        prepare_plugin_admission=prepare_admission,
                    ),
                )
            )
        except RuntimeApplyError as error:
            kernel = (
                self._app.core.plugin_manager if self._app.core is not None else None
            )
            if (
                kernel is not None
                and admitted_plugin is not None
                and activation_requested
            ):
                await kernel.fail_admission_activation(candidate_id, fingerprint, error)
            raise
        original = self._candidate(candidate_id, fingerprint)
        kernel = self._app.core.plugin_manager if self._app.core is not None else None
        state = (
            next(
                (row for row in kernel.states() if row["candidate_id"] == candidate_id),
                {},
            )
            if kernel is not None
            else {}
        )
        return {
            **result,
            "operation_id": operation_id,
            "plugin_id": original.manifest.id,
            "candidate_id": candidate_id,
            "restart_required": state.get("state") == "RESTART_REQUIRED",
            "state": state.get("state", "DISCOVERED"),
            "error": state.get("error", ""),
        }
