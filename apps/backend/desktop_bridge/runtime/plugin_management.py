"""Plugin management channel: enumerate plugins and hot toggle enablement.

Owns the ``plugins.list``/``plugins.setEnabled`` request bodies (and hosts the
``channels.list`` listing derived from plugin channel declarations) so
``ReloadableDesktopService`` only has to dispatch, not implement discovery
or the enable/disable write path itself.

Enable state lives in ``[plugins.<id>].enabled``. Historical preference
upgrade belongs to the configuration loading boundary.

Toggling reuses the transactional settings-apply pipeline of
``plugin.config.set``: the flag is spliced into the plugin's table inside the
settings lock, and the plugin is loaded or unloaded within the current
generation (``PluginKernel.set_enabled``, #858). Only closures with channels
or without hot-unload support, and plugins in a state only a fresh load can
retry, still swap the generation.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.plugin_host.kernel import (
    PLUGIN_ENABLED_CONFIG_KEY,
    PluginKernel,
    plugin_enabled,
)
from shiori_sdk.core.memory import MEMORY_ENGINE
from agent.plugin_host.manifest import PluginManifest
from bootstrap.app import AppRuntime
from desktop_bridge.runtime.channel_listing import RuntimeChannelListing
from desktop_bridge.runtime.plugin_trust import RuntimePluginTrust
from desktop_bridge.runtime.plugin_packages import RuntimePluginPackages
from desktop_bridge.runtime.plugin_package_listing import (
    external_source_row,
    with_package_operations,
)
from desktop_bridge.plugin_config_text import merge_plugin_table
from desktop_bridge.runtime.apply import (
    DerivedWrite,
    RuntimeApplyError,
    RuntimeSettingsApplication,
    assert_plugin_table_isolated,
    read_plugin_table,
)


def memory_engine_provider(kernel: PluginKernel | None) -> str | None:
    """The ACTIVE plugin that currently provides ``MEMORY_ENGINE``, if any.

    A declared ``provides`` entry is not enough: setup failure releases the
    socket, and ``get`` is then None.
    """
    if kernel is None or kernel.kernel.get(MEMORY_ENGINE) is None:
        return None
    # The SDK kernel keeps a key's owner private and has no LOC budget left for
    # an owner lookup, so the owner is read off the manifests. Planning refuses
    # two live plugins declaring the same key, so at most one ACTIVE one does.
    active = set(kernel.active_plugin_ids)
    for record in kernel.discover():
        if record.manifest.id in active and "memory_engine" in record.manifest.provides:
            return record.manifest.id
    return None


class RuntimePluginManagement:
    """Lists discovered plugins and toggles their enablement via config state."""

    def __init__(self, app: AppRuntime, settings: RuntimeSettingsApplication) -> None:
        self._app = app
        self._settings = settings
        self.trust = RuntimePluginTrust(app, settings)
        self.packages = RuntimePluginPackages(self, app.workspace)
        self.channels = RuntimeChannelListing(app, self._enabled)

    def memory_provider(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """``memory.provider``: the plugin id filling ``MEMORY_ENGINE``, or null."""
        return {"plugin_id": memory_engine_provider(self._plugin_kernel())}

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
                    **self.trust.describe(record),
                    "candidate_id": record.candidate_id,
                    "source": record.source,
                    "directory": str(record.plugin_dir),
                    "name": record.manifest.display_name or record.name,
                    "version": record.manifest.version or "",
                    "description": record.manifest.desc or "",
                    # Static declarations are data only; Electron grants resources
                    # exclusively for unique ACTIVE workspace candidates.
                    "renderer": record.manifest.metadata.get("renderer", {}),
                    # Main-process resources must use the approved startup bytes,
                    # never establish a newer baseline during their first request.
                    "content_fingerprint": record.fingerprint,
                    "content_hashes": record.content_hashes,
                    "enabled": self._enabled(record.manifest),
                    "can_toggle": runtime_state
                    not in {"CONFLICT", "UNTRUSTED", "BLOCKED", "RESTART_REQUIRED"},
                    "supports_hot_unload": record.manifest.supports_hot_unload,
                    "dependencies": list(record.manifest.dependencies),
                    # Declared capabilities and static channel declarations let
                    # the desktop group channel plugins without activating them.
                    "capabilities": list(record.manifest.capabilities),
                    "inject": list(record.manifest.inject),
                    "channels": [
                        declaration.to_dict()
                        for declaration in record.manifest.channels
                    ],
                    # Settings › 插件 groups its rows by this (feature/channel/system).
                    "category": record.manifest.category,
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
                    # Required renderer entries (ui/background) not yet
                    # confirmed ready by their owning window; non-empty only
                    # while ``state == "ACTIVE"`` (#262 AC1).
                    "pending_renderer_kinds": (
                        state.get("pending_renderer_kinds", []) if state else []
                    ),
                    # Opaque per-activation-attempt identity, echoed back in
                    # ``plugins.activation.report`` so a stale report from a
                    # disable/re-enable cycle's abandoned load cannot be
                    # mistaken for the current handle (#262).
                    "activation_token": (
                        state.get("activation_token", "") if state else ""
                    ),
                    # Saved accounts the running plugin could not register
                    # (e.g. no owner role); the plugin itself stays up.
                    "account_errors": self._settings.roles.accounts.rejected(plugin_id),
                    # __contains__ 已随 #177 的死代码清理移除，改用 schema_for 判定
                    "has_config_schema": kernel.config_schemas.schema_for(plugin_id)
                    is not None,
                }
            )
        # Only the roster sees uninstalled external sources; they never enter
        # discovery, so no load, trust, package or channel path can reach them.
        # Added after package operations: a queued install of the same ID (not
        # yet in this generation's discovery) already answers the diagnostic.
        rows = with_package_operations(plugins, self.packages.store)
        listed = {row["id"] for row in rows}
        rows.extend(
            external_source_row(source)
            for source in kernel.uninstalled_external_sources()
            if source.manifest.id not in listed
        )
        return {"plugins": rows}

    async def set_enabled(
        self,
        payload: dict[str, Any],
        *,
        prepare_service: Callable,
        publish_service: Callable,
    ) -> dict[str, Any]:
        """Persists a plugin's enabled flag and loads or unloads it in the generation.

        ``reloaded_plugins`` in the result lists the plugins loaded or unloaded
        (the target and the plugins that depend on it); it is absent when the
        state did not change or a generation swap applied the change.
        """
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
                reload_plugin=plugin_id,
                toggle=True,
            ),
        )
        return {"plugin_id": plugin_id, "enabled": enabled, **result}

    async def report_activation(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Applies one renderer's ui/background/surface activation outcome (#262).

        Called by a renderer window (main window, plugin-host background
        window, or a surface window) once it has loaded — or failed to load —
        a `renderer.<kind>` entry the backend already admitted for an ACTIVE
        plugin. Idempotent and safe against stale/duplicate reports: a report
        naming a plugin/kind the current generation's kernel is not tracking
        as ACTIVE is silently ignored (``changed: False``) rather than
        raising, since a renderer process cannot synchronously know the
        backend's current view — see ``PluginKernel._find_active_handle``.
        """
        plugin_id = str(payload.get("plugin_id") or "").strip()
        kind = str(payload.get("kind") or "").strip()
        ok = payload.get("ok")
        if not plugin_id or kind not in {"ui", "background", "surface"}:
            raise RuntimeApplyError(
                "runtime_invalid_request", "plugin_id 和 kind 不能为空或非法"
            )
        if not isinstance(ok, bool):
            raise RuntimeApplyError("runtime_invalid_request", "ok 必须是布尔值")
        activation_token = str(payload.get("activation_token") or "")
        kernel = self._plugin_kernel()
        changed = False
        if kernel is not None:
            if ok:
                changed = await kernel.confirm_renderer_entry(
                    plugin_id, kind, activation_token
                )
            else:
                reason = str(payload.get("reason") or "renderer 报告激活失败").strip()
                changed = await kernel.fail_renderer_entry(
                    plugin_id, kind, reason or "renderer 报告激活失败", activation_token
                )
        return {"plugin_id": plugin_id, "kind": kind, "changed": changed}

    def _enabled(self, manifest: PluginManifest) -> bool:
        """Reports the effective enable flag, honouring the manifest default."""
        return plugin_enabled(manifest, self._app.config.plugins.get(manifest.id, {}))

    def _plugin_kernel(self) -> "PluginKernel | None":
        """Returns the currently published generation's plugin kernel, if any."""
        core = self._app.core
        return core.plugin_manager if core is not None else None
