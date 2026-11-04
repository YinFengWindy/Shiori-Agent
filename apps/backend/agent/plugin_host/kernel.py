"""插件内核：发现、装配、生命周期与失败回滚。

内核只拥有"插件如何被装配、启动、停止和清理"；回合事件语义、
工具错误路径等产品语义仍由 Shiori 核心模块定义。
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Callable, Iterable, Sequence
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

from agent.plugin_host.renderer_communication import RendererCommunication
from agent.plugin_host.core_keys import (
    CoreModule,
)
from agent.plugin_host.config_schema import (
    PluginConfigSchemaRegistry,
)
from agent.plugin_host.discovery import (
    ExternalSourceDiagnostic,
    discover_plugins,
    find_uninstalled_external_sources,
)
from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.record import PluginRecord, find_record, records_by_id
from agent.plugin_host.settings import PluginGenerationSettings, plugin_enabled
from agent.plugin_host import admission, closures, renderer_gate
from agent.plugin_host.plugin_setup import (
    activate_plugins,
    build_spec,
    dependency_api,
    purge_modules,
)
from agent.plugin_host.state import NOT_STARTED, PluginInstance, PluginView, plugin_view
from agent.plugin_host.package_fingerprint import (
    PackageContent,
)
from agent.plugin_host.reload import (
    ConfigTables,
    PluginReloadResult,
    ProcessResourceHold,
    ReloadSteps,
    reload_closure,
    toggle_closure,
)
from agent.plugin_host.unload import (
    PluginReloadUnsupported,
)
from shiori_sdk.kernel import (
    Kernel,
    KernelState,
    PluginSpec,
)

# 每个内核代际都需要独立的包命名空间。使用进程内序号而不是发现根目录
# 名称，避免插件从仓库搬到任意目录后改变 import 名称，也避免两个发现根
# 恰好同名时污染 sys.modules。
_KERNEL_NAMESPACE_COUNTER = itertools.count(1)


class PluginKernel:
    """宿主装配层：发现、准入、信任与 capability 注入，生命周期交给 ``shiori_sdk.kernel``。

    每个无冲突的插件记录对应内核里的一个 ``PluginSpec``。宿主按内核顺序逐个激活选中的
    插件。指纹与执行身份在 plan 之前复核；spec 的 setup 只用复核过的内容导入，
    并拒绝未经宿主准备的启动。``runnable`` 只表示准入通过且已启用，启动失败的
    插件仍参与依赖与冲突判定，但不会因另一个插件启动而重试。
    """

    def __init__(
        self,
        plugin_dirs: list[Path],
        *,
        settings: PluginGenerationSettings,
        core: Sequence[CoreModule],
        core_checks: Callable[[Kernel], None],
        communication: RendererCommunication,
        resolve_reference: Callable[[str], str],
        namespace: str = "",
        strict: bool = False,
        external_plugin_dirs: list[Path] | None = None,
        discovery_snapshot: list[PluginRecord] | None = None,
    ) -> None:
        """``core`` lists the core modules providing their keys to this generation.

        They provide before any plugin is planned; one that raises aborts the
        construction, and with it startup (§8.5), unlike a plugin's setup failure.
        ``core_checks`` installs the core's post-chain checks on the kernel
        (``agent.core.turn_events.install_core_checks``; this layer may not
        import the core). ``communication`` only withdraws renderer owners;
        bootstrap binds its peer resolver after construction. ``resolve_reference``
        supplies the host configuration expansion without publishing an internal Key.
        """
        self._dirs = plugin_dirs
        self._external_dirs = external_plugin_dirs or []
        self._settings = settings
        self._namespace = namespace or f"g{next(_KERNEL_NAMESPACE_COUNTER)}"
        # Settings generations retain the application's startup admission, but
        # own independent descriptors and import namespaces. Only a fresh app
        # without a supplied snapshot scans added/updated/deleted directories.
        self._records = (
            [
                replace(
                    record,
                    import_path=f"akasic_plugin_{self._namespace}_{record.manifest.id}",
                )
                for record in deepcopy(discovery_snapshot)
            ]
            if discovery_snapshot is not None
            else None
        )
        self._strict = strict
        self._instances: dict[str, PluginInstance] = {}
        self._host_failures: dict[str, Exception] = {}
        # Screened package content per candidate id, from the check before the
        # plan until the spec setup imports exactly these verified bytes.
        self._screened: dict[str, PackageContent | None] = {}
        self._kernel = Kernel()
        for module in core:
            module(self._kernel.provide)
        core_checks(self._kernel)
        self._resolve_reference = resolve_reference
        self._communication = communication
        # Serializes load/unload/reload/drain/terminate so a reload never
        # interleaves with another transition or the generation's retirement.
        self._transition_lock = asyncio.Lock()
        self._retired = False
        self.config_schemas = PluginConfigSchemaRegistry()

    def active_peers(self, plugin_id: str) -> tuple[str, ...] | None:
        """Reads dependency declarations only while the current instance is active."""
        if plugin_id not in self.active_plugin_ids:
            return None
        record = records_by_id(self.discover())[plugin_id]
        return (*record.manifest.dependencies, *record.manifest.optional_dependencies)

    # ── 发现 ──────────────────────────────────────────────────────────────

    def discover(self) -> list[PluginRecord]:
        """Return the startup candidates, isolated for this runtime generation."""
        if self._records is None:
            self._records = self.inspect_candidates()
        return list(self._records)

    def inspect_candidates(self) -> list[PluginRecord]:
        """Inspect current packages for manual trust without changing startup admission."""
        return discover_plugins(
            self._dirs,
            external_roots=self._external_dirs,
            namespace=self._namespace,
            strict=self._strict,
            workspace=self._settings.workspace,
            is_trusted=self._settings.is_trusted,
        )

    async def admit_trusted_candidate(self, candidate: PluginRecord) -> None:
        """Replace one verified startup candidate without changing enablement."""
        async with self._transition_lock:
            self._records = admission.admit_trusted_candidate(
                self.discover(),
                candidate,
                retired=self._retired,
                view=self._view,
                is_trusted=self._settings.is_trusted,
            )
            # Clearing static admission does not disable a waiting consumer.
            # Keep its runtime BLOCKED state/cause so the normal enable
            # closure can recover it when its approved provider starts.

    async def fail_admission_activation(
        self, candidate_id: str, fingerprint: str, error: Exception
    ) -> None:
        """Remember only a first trusted activation that never reached the kernel."""
        async with self._transition_lock:
            admission.fail_activation(
                find_record(self.discover(), candidate_id),
                fingerprint,
                error,
                self._kernel,
                self._host_failures,
            )

    def uninstalled_external_sources(self) -> list[ExternalSourceDiagnostic]:
        """Display-only reports for external sources this generation did not discover."""
        return find_uninstalled_external_sources(
            self._dirs, external_roots=self._external_dirs, discovered=self.discover()
        )

    # ── 加载 ──────────────────────────────────────────────────────────────

    async def load_all(self) -> None:
        """Plan discovered candidates and activate the enabled, admitted plugins."""
        async with self._transition_lock:
            await self._load_records(self.discover())

    @property
    def namespace(self) -> str:
        """Generation id the process-resource owner publishes and retains under."""
        return self._namespace

    async def _load_records(
        self, wanted: list[PluginRecord], reactivating: frozenset[str] = frozenset()
    ) -> None:
        """Preflight the selection before setting up its members in kernel order."""
        try:
            activate = await admission.plan_activations(
                wanted,
                records=records_by_id(self.discover()),
                kernel=self._kernel,
                settings=self._settings,
                host_failures=self._host_failures,
                screened=self._screened,
                make_spec=self._spec,
            )
            await activate_plugins(
                activate, reactivating, self._kernel, self._instances
            )
        finally:
            self._screened.clear()

    def _spec(self, record: PluginRecord) -> PluginSpec:
        return build_spec(
            record,
            kernel=self._kernel,
            settings=self._settings,
            communication=self._communication,
            namespace=self._namespace,
            config_schemas=self.config_schemas,
            resolve_reference=self._resolve_reference,
            dependency_api=self._dependency_api,
            prepared=self._prepared,
        )

    def _prepared(
        self, record: PluginRecord
    ) -> tuple[PluginInstance, PackageContent | None]:
        return admission.prepared(
            record,
            records=records_by_id(self.discover()),
            instances=self._instances,
            screened=self._screened,
            settings=self._settings,
        )

    # ── 渲染入口激活汇总（#262） ────────────────────────────────────────────

    async def confirm_renderer_entry(
        self, plugin_id: str, kind: str, activation_token: str
    ) -> bool:
        """Confirm one renderer contribution without changing backend resource grants."""
        return renderer_gate.confirm_entry(
            plugin_id,
            kind,
            activation_token,
            instances=self._instances,
            active_plugin_ids=self.active_plugin_ids,
        )

    async def fail_renderer_entry(
        self, plugin_id: str, kind: str, reason: str, activation_token: str
    ) -> bool:
        """Serialize renderer rollback with replacements, then recheck the attempt token."""
        async with self._transition_lock:
            changed = await renderer_gate.fail_entry(
                plugin_id,
                kind,
                reason,
                activation_token,
                kernel=self._kernel,
                instances=self._instances,
                active_plugin_ids=self.active_plugin_ids,
            )
            if changed:
                purge_modules(records_by_id(self.discover())[plugin_id].import_path)
            return changed

    # ── 卸载 ──────────────────────────────────────────────────────────────

    def assert_hot_unloadable(self, name: str | None = None) -> None:
        """Reject an unsafe closure before releasing any accepted resources."""
        closures.assert_hot_unloadable(
            name, self.discover(), self.active_plugin_ids, self._kernel
        )

    async def reload(
        self,
        name: str,
        *,
        values: dict[str, Any],
        raw_values: dict[str, Any],
        drain_timeout: float,
        commit: Callable[[tuple[str, ...]], None] | None = None,
        on_replaced: Callable[[tuple[str, ...]], None] | None = None,
    ) -> PluginReloadResult:
        """Re-runs setup of an ACTIVE plugin with new config, within this generation.

        ``values``/``raw_values`` replace the plugin table in
        ``PluginGenerationSettings.plugin_configs``/``raw_plugin_configs`` (the live
        generation config); the enable flag inside them must stay on
        (``ValueError`` otherwise). The closure (target plus ACTIVE plugins
        that inject it, through ``inject`` or ``optional_inject``) is sealed,
        drained within ``drain_timeout`` seconds and disposed dependents-first,
        then set up again target-first with ``was_active`` / ``is_reload`` True
        on the ``RUNTIME`` key. Plugins outside it are untouched; the closure's
        process resources survive.

        ``commit`` (given the reloaded plugin ids) persists the new config
        once every closure plugin is ACTIVE with it. It runs synchronously in
        the same uninterruptible replacement as the setup, so caller
        cancellation cannot separate "reloaded" from "persisted"; when it
        raises, the reload is rolled back like a setup failure of the target.
        ``on_replaced`` receives the full closure once its final instances have
        settled, including failed restores, inside that same uninterruptible
        transition. It announces replacement independently of config success.

        Raises, with nothing changed: ``LookupError`` for an unknown plugin,
        ``PluginReloadUnsupported`` when no in-generation reload applies, and
        ``PluginReloadTimeout`` (or the ``on_drain`` error, or cancellation)
        when draining did not finish. Raises ``PluginReloadFailed`` after
        restoring the old tables and instances when the new config fails.
        See ``agent.plugin_host.reload`` for the transition itself.
        """
        async with self._transition_lock:
            record = find_record(self.discover(), name)
            if record is None:
                raise LookupError(f"未找到插件: {name}")
            closure = closures.reload_closure(
                self._view(record), self.views(), self._kernel, self._retired
            )
            if not plugin_enabled(record.manifest, values):
                raise ValueError(f"重载不能停用插件 {record.manifest.id}")
            return await reload_closure(
                record.manifest.id,
                closure,
                values=values,
                raw_values=raw_values,
                tables=ConfigTables(
                    self._settings.plugin_configs, self._settings.raw_plugin_configs
                ),
                steps=self._reload_steps(),
                drain_timeout=drain_timeout,
                commit=commit,
                on_replaced=on_replaced,
            )

    def _records_for_ids(self, plugin_ids: Iterable[str]) -> list[PluginRecord]:
        records = records_by_id(self.discover())
        return [records[plugin_id] for plugin_id in plugin_ids]

    def _reload_steps(self, *, disabled: frozenset[str] = frozenset()) -> ReloadSteps:
        async def dispose(record: PluginRecord) -> list[Exception]:
            plugin_id = record.manifest.id
            self._communication.remove_plugin(
                plugin_id,
                reason=(
                    "plugin_disabled" if plugin_id in disabled else "plugin_reloading"
                ),
            )
            return await self._dispose_record(record)

        def calls(record: PluginRecord) -> PluginCallGate | None:
            instance = self._instances.get(record.manifest.id)
            return instance.calls if instance is not None else None

        return ReloadSteps(
            drain=lambda records, timeout: closures.drain_closure(
                records, timeout, self._kernel, self._instances
            ),
            dispose=dispose,
            activate=self._activate_reloaded,
            retain=self._retain_process_resources,
            calls=calls,
        )

    async def set_enabled(
        self,
        name: str,
        *,
        values: dict[str, Any],
        raw_values: dict[str, Any],
        drain_timeout: float,
        commit: Callable[[tuple[str, ...]], None] | None = None,
        on_replaced: Callable[[tuple[str, ...]], None] | None = None,
    ) -> PluginReloadResult:
        """Enables or disables a plugin within this generation, as ``values`` say.

        ``values``/``raw_values`` replace the plugin table like ``reload``; the
        enable flag inside them decides the direction.

        - Disabling an ACTIVE plugin disposes it and the ACTIVE plugins that
          hard-depend on it without draining (in-flight work is cancelled, as
          on a generation swap) and closes their process resources; they are
          left DISABLED or BLOCKED. A FAILED or dependency-BLOCKED target only
          becomes DISABLED.
        - Enabling a DISABLED plugin loads it and the dependency-BLOCKED
          plugins it unblocks. A setup failure leaves that plugin FAILED (and
          the change persisted), as a generation swap would.
        - Either way the ACTIVE plugins that inject the target through
          ``optional_inject`` / ``optional_dependencies`` (and their hard
          dependents) stay ACTIVE but are drained like on a ``reload`` and set
          up again after the change, with ``was_active`` / ``is_reload`` True,
          so none keeps the provider state it read before. A failing setup
          leaves such a plugin FAILED, as for the plugins toggled.
        - When the plugin's state does not change, only the tables are replaced
          (``plugin_ids`` empty).

        ``commit`` (given the affected plugin ids) persists the change inside
        the same uninterruptible transition; when it raises, the previous tables
        and states are restored and ``PluginReloadFailed`` (or, when nothing was
        loaded or unloaded, the commit error itself) is raised. Raises, with
        nothing changed: ``PluginReloadUnsupported`` when only a generation
        swap applies (the generation is retired, the closure has channels or
        cannot be hot unloaded, or a plugin involved is in a state only a swap
        can retry), and ``PluginReloadTimeout`` (or the ``on_drain`` error, or
        cancellation) when draining the optional consumers did not finish: a
        busy consumer refuses the toggle, disabling included, and ``commit``
        never runs. See ``agent.plugin_host.reload.toggle_closure``.
        ``on_replaced`` has the same settled-instance semantics as ``reload``;
        a table-only change does not call it.
        """
        async with self._transition_lock:
            record = find_record(self.discover(), name)
            if record is None:
                raise LookupError(f"未找到插件: {name}")
            plugin_id = record.manifest.id
            if self._retired:
                raise PluginReloadUnsupported([plugin_id], "retired")
            target = self._view(record)
            enabled = plugin_enabled(record.manifest, values)
            tables = ConfigTables(
                self._settings.plugin_configs, self._settings.raw_plugin_configs
            )
            if enabled:
                closure = (
                    closures.enable_closure(
                        target, self.views(), self.active_plugin_ids, self._kernel
                    )
                    if target.state == "DISABLED" or target.diagnostic == NOT_STARTED
                    else None
                )
            else:
                closure = closures.disable_closure(target, self.views(), self._kernel)
            if closure is None:
                previous = tables.swap(plugin_id, values, raw_values)
                try:
                    if commit is not None:
                        commit(())
                except BaseException:
                    _ = tables.swap(plugin_id, *previous)
                    raise
                return PluginReloadResult((), ())
            closures.refuse_restart_only(closure, self._kernel)
            # What the toggle itself takes down or brings up: the target and
            # its running hard dependents. The other ACTIVE members stay up.
            toggled = set(self._kernel.closure(plugin_id, optional=False))
            staying = frozenset(
                handle.plugin_id
                for handle in closure
                if handle.state == "ACTIVE" and handle.plugin_id not in toggled
            )
            result = await toggle_closure(
                plugin_id,
                closure,
                enabled=enabled,
                staying=staying,
                values=values,
                raw_values=raw_values,
                tables=tables,
                steps=self._reload_steps(
                    disabled=frozenset(toggled) if not enabled else frozenset()
                ),
                drain_timeout=drain_timeout,
                commit=commit,
                on_replaced=on_replaced,
            )
            if not enabled:
                # A later re-enable within this generation is a fresh start.
                self._settings.previously_active_plugins -= (
                    frozenset(result.plugin_ids) - staying
                )
            return result

    async def _activate_reloaded(
        self, record: PluginRecord, reactivating: frozenset[str]
    ) -> PluginView:
        await self._load_records([record], reactivating)
        return self._view(record)

    def _retain_process_resources(
        self, plugin_ids: tuple[str, ...]
    ) -> ProcessResourceHold | None:
        owner = self._settings.process_resources
        return None if owner is None else owner.retain(self._namespace, plugin_ids)

    async def _dispose_record(self, record: PluginRecord) -> list[Exception]:
        plugin_id = record.manifest.id
        if (instance := self._instances.get(plugin_id)) is not None:
            instance.calls.retire()
        errors = await self._kernel.deactivate(plugin_id)
        self._instances.pop(plugin_id, None)
        self._host_failures.pop(record.candidate_id, None)
        self.config_schemas.unregister(plugin_id)
        purge_modules(record.import_path)
        return errors

    async def terminate_all(self, *, force: bool = False) -> None:
        """Preflights all active plugins, or forcibly releases them on process exit."""
        async with self._transition_lock:
            await self._terminate_all(force=force)

    async def _terminate_all(self, *, force: bool) -> None:
        if not force:
            self.assert_hot_unloadable()
        self._retired = True
        errors: list[Exception] = []
        # Include scopes whose setup/release was interrupted, even without an
        # ACTIVE status or a position in the current plan.
        records = self._records_for_ids(
            dict.fromkeys((*reversed(self._kernel.order()), *reversed(self._instances)))
        )
        for record in records:
            errors.extend(await self._dispose_record(record))
        if errors:
            raise ExceptionGroup("Plugin cleanup failed", errors)

    def _dependency_api(self, plugin_id: str, optional: bool = False) -> Any:
        return dependency_api(plugin_id, optional, self._kernel, self.active_plugin_ids)

    async def drain(self) -> None:
        """Wait for accepted work while the retiring transport is still attached."""
        async with self._transition_lock:
            for plugin_id in reversed(self.active_plugin_ids):
                await self._kernel.scope(plugin_id).drain()

    # ── 聚合面（供宿主接线） ────────────────

    def _view(self, record: PluginRecord) -> PluginView:
        return plugin_view(
            record,
            plugin_enabled(
                record.manifest,
                self._settings.plugin_configs.get(record.manifest.id, {}),
            ),
            self._kernel.status(record.manifest.id),
            self._host_failures.get(record.candidate_id),
            self._instances.get(record.manifest.id),
        )

    def views(self) -> list[PluginView]:
        """Snapshots of every candidate, including those never admitted or started."""
        rank = {pid: index for index, pid in enumerate(self._kernel.order())}
        records = sorted(
            self.discover(),
            key=lambda record: (
                rank.get(record.manifest.id, -1),
                record.manifest.id,
                record.candidate_id,
            ),
        )
        return [self._view(record) for record in records]

    def view(self, name: str) -> PluginView | None:
        """Find one candidate by its directory identity or unique plugin id."""
        record = find_record(self.discover(), name)
        return self._view(record) if record is not None else None

    @property
    def kernel(self) -> Kernel:
        """The generation's kernel, with the core checks; turn events go through it."""
        return self._kernel

    @property
    def active_plugin_ids(self) -> list[str]:
        """Running plugin ids in setup order, including active plan exclusions."""
        rank = {pid: index for index, pid in enumerate(self._kernel.order())}
        return sorted(
            (
                pid
                for pid in self._instances
                if (status := self._kernel.status(pid)) is not None
                and status.state is KernelState.ACTIVE
                and self._kernel.scope(pid).active
            ),
            key=lambda pid: (rank.get(pid, -1), pid),
        )
