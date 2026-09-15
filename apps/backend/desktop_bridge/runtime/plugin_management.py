"""Plugin management channel: enumerate plugins and hot toggle enablement.

Owns the ``plugins.list``/``plugins.setEnabled`` request bodies so
``ReloadableDesktopService`` only has to dispatch, not implement discovery
or the enable/disable write path itself.

Enable state lives in ``[plugins.<id>].enabled``. Historical preference
upgrade belongs to the configuration loading boundary.

Toggling reuses the exact same transactional settings-apply pipeline as
``plugin.config.set`` (#177): any write to the ``plugins`` table changes
``AppConfig.plugins``, so ``RuntimeSettingsApplication._apply``'s
identity fast-path never applies to it regardless of entry point — the
full prepare/publish generation swap always runs, which is also how the
kernel picks up the new enabled state (a fresh ``PluginKernel.load_all()``
skips a config-disabled plugin; see ``PluginKernel._config_enabled``).
This is consistent with #177's established behavior rather than a new
"lighter" mechanism; a true single-plugin hot patch that leaves every
other plugin's in-memory state untouched would need its own
partial-generation-apply design and is left as a follow-up rather than
invented ad hoc here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.plugin_host.kernel import PLUGIN_ENABLED_CONFIG_KEY, PluginKernel
from bootstrap.app import AppRuntime
from desktop_bridge.plugin_config_text import merge_plugin_table
from desktop_bridge.runtime.apply import (
    DerivedWrite,
    RuntimeApplyError,
    RuntimeSettingsApplication,
    assert_plugin_table_isolated,
    read_plugin_table,
)


class RuntimePluginManagement:
    """Lists discovered plugins and toggles their enablement via config state."""

    def __init__(self, app: AppRuntime, settings: RuntimeSettingsApplication) -> None:
        self._app = app
        self._settings = settings

    def list(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """Returns every discovered plugin with its enabled flag and runtime state."""
        kernel = self._plugin_kernel()
        if kernel is None:
            return {"plugins": []}
        states = {entry["candidate_id"]: entry for entry in kernel.states()}
        plugins: list[dict[str, Any]] = []
        for record in kernel.discover():
            plugin_id = record.manifest.id
            state = states.get(record.candidate_id)
            admission = record.admission
            runtime_state = (
                state["state"]
                if state
                else (admission.state if admission else "DISCOVERED")
            )
            plugins.append(
                {
                    "id": plugin_id,
                    "candidate_id": record.candidate_id,
                    "source": record.source,
                    "directory": str(record.plugin_dir),
                    "name": record.name,
                    "version": record.manifest.version or "",
                    "description": record.manifest.desc or "",
                    # Static declarations are data only; Electron grants resources
                    # exclusively for unique ACTIVE workspace candidates.
                    "renderer": record.manifest.metadata.get("renderer", {}),
                    "enabled": self._enabled(plugin_id),
                    "can_toggle": runtime_state
                    not in {"CONFLICT", "UNTRUSTED", "BLOCKED"},
                    "supports_hot_unload": record.manifest.supports_hot_unload,
                    "dependencies": list(record.manifest.dependencies),
                    "state": runtime_state,
                    "error": (
                        state["error"]
                        if state
                        else (admission.reason if admission else "")
                    ),
                    "diagnostic": (
                        state.get("diagnostic")
                        if state
                        else (admission.to_dict() if admission else None)
                    ),
                    # __contains__ 已随 #177 的死代码清理移除，改用 schema_for 判定
                    "has_config_schema": kernel.config_schemas.schema_for(plugin_id)
                    is not None,
                }
            )
        return {"plugins": plugins}

    async def set_enabled(
        self,
        payload: dict[str, Any],
        *,
        prepare_service: Callable,
        publish_service: Callable,
    ) -> dict[str, Any]:
        """Persists a plugin's enabled flag and hot-applies it via a generation swap."""
        plugin_id = str(payload.get("plugin_id") or "").strip()
        enabled = payload.get("enabled")
        operation_id = payload.get("operation_id")
        if not plugin_id:
            raise RuntimeApplyError("runtime_invalid_request", "plugin_id 不能为空")
        if not isinstance(enabled, bool):
            raise RuntimeApplyError("runtime_invalid_request", "enabled 必须是布尔值")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise RuntimeApplyError("runtime_invalid_request", "操作 ID 不能为空")
        candidates = [row for row in self.list({})["plugins"] if row["id"] == plugin_id]
        if not candidates:
            raise RuntimeApplyError("plugin_not_found", f"插件 {plugin_id} 不存在")
        if len(candidates) != 1 or not candidates[0]["can_toggle"]:
            raise RuntimeApplyError(
                "plugin_not_admitted",
                candidates[0]["error"] or f"插件 {plugin_id} 未通过准入检查",
            )

        # 只翻一个开关、其余字段沿用当前已提交的配置，所以基准表必须在事务锁内
        # 读取：在锁外读会把并发落地的 runtime.apply 或 plugin.config.set 整份覆盖。
        def _merge(current_text: str) -> str:
            stored = read_plugin_table(current_text, plugin_id)
            stored[PLUGIN_ENABLED_CONFIG_KEY] = enabled
            merged = merge_plugin_table(current_text, plugin_id, stored)
            assert_plugin_table_isolated(plugin_id, current_text, merged)
            return merged

        apply_payload: dict[str, Any] = {"operation_id": operation_id}
        expected_generation = payload.get("expected_generation")
        if expected_generation is not None:
            apply_payload["expected_generation"] = expected_generation
        result = await self._settings.apply(
            apply_payload,
            prepare_service=prepare_service,
            publish_service=publish_service,
            # 幂等指纹取本次逻辑操作（哪个插件、开还是关），而不是派生出来的
            # 整份配置文本：后者会随无关设置的变化而变，同一请求原样重试就会被
            # 误判为 runtime_operation_conflict。
            derive=DerivedWrite(
                build_config_toml=_merge,
                fingerprint_payload={"plugin_id": plugin_id, "enabled": enabled},
            ),
        )
        return {"plugin_id": plugin_id, "enabled": enabled, **result}

    def _enabled(self, plugin_id: str) -> bool:
        stored = self._app.config.plugins.get(plugin_id, {})
        return bool(stored.get(PLUGIN_ENABLED_CONFIG_KEY, True))

    def _plugin_kernel(self) -> "PluginKernel | None":
        """Returns the currently published generation's plugin kernel, if any."""
        core = self._app.core
        return core.plugin_manager if core is not None else None
