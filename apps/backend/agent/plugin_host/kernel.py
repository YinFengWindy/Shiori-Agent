"""插件内核：发现、装配、生命周期与失败回滚。

内核只拥有"插件如何被装配、启动、停止和清理"；回合事件语义、
工具错误路径等产品语义仍由 Shiori 核心模块定义。
"""

from __future__ import annotations

import asyncio
import importlib.util
import itertools
import logging
import sys
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field, replace
from importlib.abc import Loader
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from agent.plugin_host.services import ScopedPluginServices
from agent.plugin_host.config import PluginConfig
from agent.plugin_host.kv import PluginKVStore, open_plugin_kv
from agent.plugin_host.core_keys import (
    HOST_BRIDGE,
    HOST_CONFIG_REFERENCES,
    CoreModule,
    PluginBinding,
    required_core_key,
)
from agent.plugin_host.config_schema import (
    PluginConfigSchemaRegistry,
    resolve_config_model,
)
from agent.plugin_host.dependencies import PluginDependencies, PluginDependencyError
from agent.plugin_host.discovery import (
    TrustCheck,
    ExternalSourceDiagnostic,
    discover_plugins,
    find_uninstalled_external_sources,
    refresh_dependency_admission,
)
from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.handle import PluginRecord
from agent.plugin_host.state import NOT_STARTED, PluginInstance, PluginView, plugin_view
from agent.plugin_host.manifest import (
    ManifestError,
    PluginManifest,
)
from agent.plugin_host.package_fingerprint import (
    PackageContent,
    inspect_package_content,
)
from agent.plugin_host.runtime_context import PluginRuntimeContext
from agent.plugin_host.runtime_lifecycle import PluginRuntimeLifecycle
from agent.plugin_host.execution_identity import PluginExecutionIdentity
from agent.plugin_host.trusted_imports import TrustedPluginImports
from agent.plugin_host.reload import (
    ConfigTables,
    PluginReloadResult,
    ProcessResourceHold,
    ProcessResourceSource,
    ReloadSteps,
    hot_unload_blockers,
    reload_closure,
    toggle_closure,
)
from agent.plugin_host.unload import (
    PluginReloadTimeout,
    PluginReloadUnsupported,
    PluginRestartRequired,
)
from shiori_sdk import PluginRuntimeContext as SdkRuntimeContext
from shiori_sdk.runtime import HostServiceUnavailable
from shiori_sdk.kernel import (
    Context,
    Kernel,
    KernelError,
    KernelState,
    Key,
    PackageContractError,
    PluginDiagnostic,
    PluginSpec,
    RendererActivationError,
)

logger = logging.getLogger(__name__)

# 启停状态与插件自己的配置同住 [plugins.<id>] 表，但它归宿主所有、不是插件配置
# 模型的字段。凡是整表读写这张表的地方都必须认得这个键，否则会互相覆盖。
PLUGIN_ENABLED_CONFIG_KEY = "enabled"


def plugin_enabled(manifest: PluginManifest, stored: Mapping[str, Any]) -> bool:
    """Returns whether a plugin is enabled given its ``[plugins.<id>]`` table.

    An explicit ``enabled`` always wins; without one the manifest's
    ``default_enabled`` decides. Shared by the kernel's load gate and the
    desktop plugin/channel listings so they can never disagree.
    """
    return bool(stored.get(PLUGIN_ENABLED_CONFIG_KEY, manifest.default_enabled))


# 每个内核代际都需要独立的包命名空间。使用进程内序号而不是发现根目录
# 名称，避免插件从仓库搬到任意目录后改变 import 名称，也避免两个发现根
# 恰好同名时污染 sys.modules。
_KERNEL_NAMESPACE_COUNTER = itertools.count(1)

# Renderer contribution points whose readiness gates the *display* of a
# plugin as fully "ACTIVE" (issue #262 AC1). ``surface`` is intentionally not
# gated here: unlike ``ui`` (main window) and ``background`` (the always-on
# plugin-host window), a surface window is only created on demand, so
# waiting for it would mean a plugin whose surface nobody has opened yet
# could never leave a pending state. A surface entry that fails to load
# still rolls the whole plugin back via ``fail_renderer_entry`` — it is just
# not part of the initial admission gate.
_RENDERER_GATED_KINDS: tuple[str, ...] = ("ui", "background")


class _ActivationRefused(Exception):
    """Spec setup refused a start the host did not prepare; carries the reason."""


def plugin_key(plugin_id: str) -> Key[Any]:
    """Kernel key under which a plugin provides the API it exposes (``ctx.expose``).

    Manifest ``dependencies`` / ``optional_dependencies`` become kernel
    ``requires`` / ``optional`` on these keys, so the kernel orders setup,
    blocks dependents of an unavailable plugin and builds reload closures.
    """
    return Key(f"plugin:{plugin_id}")


@dataclass
class PluginGenerationSettings:
    """What one kernel generation itself runs on; services plugins use come from core.

    ``plugin_configs`` / ``raw_plugin_configs`` are the live ``[plugins.<id>]``
    tables: an in-generation reload or toggle swaps and rolls back entries in
    place. ``previously_active_plugins`` shrinks when a plugin is disabled
    within the generation, so a later re-enable is a fresh start.
    """

    # Execution identity and plugin KV root; None in host tests
    # without a workspace (a plugin declaring ``kv`` then fails before setup).
    workspace: Path | None = None
    plugin_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    raw_plugin_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    # The process-level owner (PROCESSES). The generation retains attachments
    # across in-generation reloads; the app publishes the active generation.
    # The core hands each plugin its attachment.
    process_resources: ProcessResourceSource | None = None
    is_reload: bool = False
    previously_active_plugins: frozenset[str] = frozenset()
    # Live activation approval supplied by bootstrap; no checker means untrusted.
    is_trusted: TrustCheck | None = None


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
        import the core).
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
        self._resolve_reference = required_core_key(
            self._kernel.get, HOST_CONFIG_REFERENCES
        )
        # Serializes load/unload/reload/drain/terminate so a reload never
        # interleaves with another transition or the generation's retirement.
        self._transition_lock = asyncio.Lock()
        self._retired = False
        # 每个 runtime generation 独立一份 RPC 注册表（bootstrap 创建，经
        # host.bridge 提供）与配置 schema 注册表；内核只绑定 communication 的
        # 依赖解析，并在插件卸载时撤销它的 renderer communication。
        self._rpc = required_core_key(self._kernel.get, HOST_BRIDGE)
        self._rpc.communication.bind_resolver(self._communication_dependencies)
        self.config_schemas = PluginConfigSchemaRegistry()

    def _communication_dependencies(self, plugin_id: str) -> tuple[str, ...] | None:
        """Reads dependency declarations only while the current instance is active."""
        if plugin_id not in self.active_plugin_ids:
            return None
        record = self._records_by_id()[plugin_id]
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
            previous = self._find_record(candidate.candidate_id)
            if (
                self._retired
                or previous is None
                or previous.source != "workspace"
                or previous.fingerprint != candidate.fingerprint
                or previous.manifest.id != candidate.manifest.id
                or candidate.admission is not None
            ):
                raise ValueError("插件候选已变化，请重新读取后确认")
            if self._view(previous).state not in {"UNTRUSTED", "BLOCKED", "DISABLED"}:
                raise ValueError("插件已执行或状态已变化，请重新读取后操作")
            records = self.discover()
            records[records.index(previous)] = candidate
            is_trusted = self._settings.is_trusted
            if is_trusted is None:
                raise ValueError("插件信任检查不可用")
            refresh_dependency_admission(records, is_trusted)
            self._records = records
            # Clearing static admission does not disable a waiting consumer.
            # Keep its runtime BLOCKED state/cause so the normal enable
            # closure can recover it when its approved provider starts.

    async def fail_admission_activation(
        self, candidate_id: str, fingerprint: str, error: Exception
    ) -> None:
        """Remember only a first trusted activation that never reached the kernel."""
        async with self._transition_lock:
            record = self._find_record(candidate_id)
            if (
                record is None
                or record.fingerprint != fingerprint
                or record.admission is not None
                or self._running(record.manifest.id)
            ):
                return
            status = self._kernel.status(record.manifest.id)
            if status is None or status.state is KernelState.STOPPED:
                self._host_failures[candidate_id] = error

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

    def _records_by_id(self) -> dict[str, PluginRecord]:
        # Conflicts remain visible as separate candidates, but cannot be resolved
        # as dependencies or loaded by choosing a preferred directory.
        return {
            record.manifest.id: record
            for record in self.discover()
            if record.admission is None or record.admission.state != "CONFLICT"
        }

    async def _load_records(
        self, wanted: list[PluginRecord], reactivating: frozenset[str] = frozenset()
    ) -> None:
        """Preflight selected plugins and newly released plan exclusions before setup."""
        records = self._records_by_id()
        selected: dict[str, PluginRecord] = {}
        pending = list(wanted)
        while pending:
            record = pending.pop(0)
            if record.candidate_id in selected:
                continue
            selected[record.candidate_id] = record
            if self._runnable(record):
                pending.extend(
                    records[pid]
                    for pid in record.manifest.dependencies
                    if pid in records
                )
        try:
            for record in selected.values():
                if self._wants_start(record):
                    self._screen(record)
            order = await self._kernel.plan(
                self._spec(record)
                for record in selected.values()
                if records.get(record.manifest.id) is record
            )
            while True:
                activate: dict[str, PluginRecord] = {}
                refused: list[PluginRecord] = []
                for plugin_id in order:
                    record = records[plugin_id]
                    if not self._wants_start(record):
                        continue
                    if (
                        record.candidate_id not in selected
                        and self._kernel.status(plugin_id) is not None
                    ):
                        continue
                    if record.candidate_id not in self._screened and not self._screen(
                        record
                    ):
                        refused.append(record)
                    else:
                        activate[plugin_id] = record
                if not refused:
                    break
                order = await self._kernel.plan(
                    self._spec(record) for record in refused
                )
            await self._start_plugins(activate, reactivating)
        finally:
            self._screened.clear()

    def _runnable(self, record: PluginRecord) -> bool:
        return record.admission is None and self._config_enabled(record.manifest)

    def _wants_start(self, record: PluginRecord) -> bool:
        """A selected plugin may start only without a scope or a restart barrier."""
        if not self._runnable(record) or self._running(record.manifest.id):
            return False
        if record.candidate_id in self._host_failures:
            return False
        status = self._kernel.status(record.manifest.id)
        return (
            status is None
            or status.state is not KernelState.FAILED
            or not status.cleanup_errors
        )

    def _screen(self, record: PluginRecord) -> bool:
        """Checks a package against its approval before it is planned runnable.

        A workspace package whose bytes no longer match the approved
        fingerprint, or whose id already executed other content in this
        desktop session, gets an ``UNTRUSTED`` / ``RESTART_REQUIRED``
        admission, so ``_spec`` makes it register-only. Otherwise the verified
        content is kept for the spec setup to import: the bytes checked here
        are the bytes executed, never read from disk again.
        """
        if record.source != "workspace":
            self._screened[record.candidate_id] = None
            return True
        try:
            content = inspect_package_content(record.plugin_dir)
            if content.fingerprint != record.fingerprint:
                raise PackageContractError(
                    "trust_changed",
                    "trust",
                    "插件内容已变化，请重启并重新确认信任",
                )
            if self._settings.workspace is not None:
                PluginExecutionIdentity(self._settings.workspace).verify(
                    record.manifest.id, record.plugin_dir, content.fingerprint
                )
        except PackageContractError as exc:
            execution_changed = exc.diagnostic.code == "executed_content_changed"
            record.admission = PluginDiagnostic(
                ("executed_content_changed" if execution_changed else "trust_changed"),
                "trust",
                "content",
                str(exc),
                str(record.plugin_dir),
                "RESTART_REQUIRED" if execution_changed else "UNTRUSTED",
            )
            return False
        self._screened[record.candidate_id] = content
        return True

    def _spec(self, record: PluginRecord) -> PluginSpec:
        """Adapt manifest dependencies and admit only a prepared source snapshot."""
        manifest = record.manifest

        async def setup(ctx: Context) -> None:
            instance, content = self._prepared(record)
            try:
                self._record_execution(record, content)
                scope = self._kernel.scope(manifest.id)
                scope.subscribe(
                    lambda: self._rpc.communication.remove_plugin(manifest.id),
                    "renderer-communication",
                )
                self._import_entry(record, content)
                self._register_config_schema(record)
                api = await self._setup_v2(record, instance, ctx)
                ctx.provide(plugin_key(manifest.id), api)
                instance.pending_renderer_kinds = _required_renderer_kinds(record)
                instance.activation_token = uuid4().hex
                logger.info("插件已加载: %s", record.name)
            except BaseException:
                instance.calls.retire()
                raise

        return PluginSpec(
            manifest.id,
            setup,
            requires=(
                *(plugin_key(d).name for d in manifest.dependencies),
                *manifest.inject,
            ),
            optional=(
                *(plugin_key(d).name for d in manifest.optional_dependencies),
                *manifest.optional_inject,
            ),
            provides=(plugin_key(manifest.id).name, *manifest.provides),
            runnable=self._runnable(record),
            hot_reload=manifest.supports_hot_unload,
            channels=_declares_channels(record),
        )

    def _find_record(self, name: str) -> PluginRecord | None:
        exact = [record for record in self.discover() if record.candidate_id == name]
        matches = exact or [
            record
            for record in self.discover()
            if record.name == name or record.manifest.id == name
        ]
        if len(matches) > 1:
            raise ManifestError(f"插件名称不唯一，请使用候选目录标识: {name}")
        return matches[0] if matches else None

    async def _start_plugins(
        self, activate: Mapping[str, PluginRecord], reactivating: frozenset[str]
    ) -> None:
        """Create host gates for exactly one activation at a time, in kernel order."""
        for plugin_id in self._kernel.order():
            if (record := activate.get(plugin_id)) is None:
                continue
            self._instances[plugin_id] = PluginInstance(
                PluginCallGate(plugin_id), reactivated=plugin_id in reactivating
            )
            try:
                await self._kernel.activate(plugin_id)
            finally:
                # Interrupted cleanup still owns a scope: retain its gates so
                # force termination can finish the remaining effects.
                if not self._running(plugin_id):
                    self._instances.pop(plugin_id, None)
                    _purge_modules(record.import_path)

    def _running(self, plugin_id: str) -> bool:
        """Whether the kernel currently holds ``plugin_id``'s scope."""
        try:
            _ = self._kernel.scope(plugin_id)
        except KeyError:
            return False
        return True

    def _prepared(
        self, record: PluginRecord
    ) -> tuple[PluginInstance, PackageContent | None]:
        """Consume this activation's preflight exactly once, before importing any code."""
        plugin_id = record.manifest.id
        instance = self._instances.get(plugin_id)
        if instance is None or self._records_by_id().get(plugin_id) is not record:
            raise _ActivationRefused(f"插件 {plugin_id} 未经宿主准备，不能启动")
        if not self._runnable(record):
            raise _ActivationRefused(f"插件 {plugin_id} 未通过准入或已禁用，不能启动")
        if record.candidate_id not in self._screened:
            raise _ActivationRefused(f"插件 {plugin_id} 的包内容未经复核，不能启动")
        return instance, self._screened.pop(record.candidate_id)

    def _record_execution(
        self, record: PluginRecord, content: PackageContent | None
    ) -> None:
        """Persists the execution identity of screened workspace content, before import."""
        if content is not None and self._settings.workspace is not None:
            PluginExecutionIdentity(self._settings.workspace).record(
                record.manifest.id, record.plugin_dir, content.fingerprint
            )

    def _config_enabled(self, manifest: PluginManifest) -> bool:
        """Reads the authoritative enable flag; absent falls back to the manifest."""
        return plugin_enabled(
            manifest, self._settings.plugin_configs.get(manifest.id, {})
        )

    def _import_entry(
        self, record: PluginRecord, content: PackageContent | None
    ) -> None:
        if content is None:
            _import_module(record.import_path, record.entry_file)
        else:
            imports = TrustedPluginImports(record.import_path, content.sources)
            imports.install()
            self._kernel.scope(record.manifest.id).effect(
                imports.remove, "trusted-source-imports"
            )
            _import_module(
                record.import_path,
                record.entry_file,
                imports.loader(record.import_path, record.entry_file),
            )

    def _register_config_schema(self, record: PluginRecord) -> None:
        """Keep a failed plugin's schema available for repair until actual disposal."""
        if (model_cls := resolve_config_model(record)) is not None:
            self.config_schemas.register(record.manifest.id, model_cls)

    async def _setup_v2(
        self, record: PluginRecord, instance: PluginInstance, kernel_context: Context
    ) -> object:
        module = sys.modules[record.import_path]
        setup = getattr(module, "setup", None)
        if not callable(setup):
            raise ManifestError(f"v2 插件 {record.name} 的入口缺少 setup(ctx) 函数")
        setup_fn = cast("Callable[[SdkRuntimeContext], Awaitable[None]]", setup)
        manifest = record.manifest
        plugin_id = manifest.id
        scope = self._kernel.scope(plugin_id)
        injected = {*manifest.inject, *manifest.optional_inject}
        settings = self._settings
        binding = PluginBinding(
            plugin_id=plugin_id,
            namespace=self._namespace,
            manifest=manifest,
            scope=scope,
            calls=instance.calls,
        )
        api: object = None

        def publish_api(value: object) -> None:
            nonlocal api
            api = value

        context = PluginRuntimeContext(
            plugin_id=plugin_id,
            plugin_dir=record.plugin_dir,
            manifest=manifest,
            effects=scope,
            config=PluginConfig(
                settings.plugin_configs.get(plugin_id, {}),
                resolve_reference=self._resolve_reference,
                raw_values=settings.raw_plugin_configs.get(plugin_id),
            ),
            dependencies=PluginDependencies(
                manifest.dependencies,
                self._dependency_api,
                optional_declared=manifest.optional_dependencies,
            ),
            kv=self._open_kv(plugin_id) if "kv" in injected else None,
            runtime=PluginRuntimeLifecycle(
                settings.is_reload or instance.reactivated,
                scope.drainers,
                was_active=instance.reactivated
                or plugin_id in settings.previously_active_plugins,
            ),
            services=(
                ScopedPluginServices(
                    self._rpc.services, plugin_id, scope, instance.calls
                )
                if "services" in injected
                else None
            ),
            publish_api=publish_api,
            kernel_context=kernel_context,
            binding=binding,
        )
        await setup_fn(context)
        return api

    def _open_kv(self, plugin_id: str) -> PluginKVStore:
        """The plugin's KV store under the generation's workspace (``kv``).

        Without a workspace a plugin declaring ``kv`` fails before setup rather
        than falling back to its package directory (#209).
        """
        workspace = self._settings.workspace
        if workspace is None:
            raise HostServiceUnavailable(
                f"插件 {plugin_id} 注入了 kv，但宿主未提供服务 workspace"
            )
        return open_plugin_kv(workspace=workspace, plugin_id=plugin_id)

    # ── 渲染入口激活汇总（#262） ────────────────────────────────────────────

    def _find_active_instance(
        self, plugin_id: str, activation_token: str
    ) -> PluginInstance | None:
        """Reject reports from an inactive or superseded activation attempt."""
        instance = self._instances.get(plugin_id)
        if (
            instance is not None
            and instance.activation_token == activation_token
            and plugin_id in self.active_plugin_ids
        ):
            return instance
        return None

    async def confirm_renderer_entry(
        self, plugin_id: str, kind: str, activation_token: str
    ) -> bool:
        """Confirm one renderer contribution without changing backend resource grants."""
        instance = self._find_active_instance(plugin_id, activation_token)
        if instance is None or kind not in instance.pending_renderer_kinds:
            return False
        instance.pending_renderer_kinds -= {kind}
        return True

    async def fail_renderer_entry(
        self, plugin_id: str, kind: str, reason: str, activation_token: str
    ) -> bool:
        """Serialize renderer rollback with replacements, then recheck the attempt token."""
        async with self._transition_lock:
            instance = self._find_active_instance(plugin_id, activation_token)
            if instance is None:
                return False
            diagnostic = PluginDiagnostic(
                f"renderer_{kind}_failed",
                kind,
                "frontend.entry",
                reason,
                state="FAILED",
            )
            instance.calls.retire()
            await self._kernel.deactivate(
                plugin_id, diagnostic, RendererActivationError(diagnostic)
            )
            self._instances.pop(plugin_id)
            _purge_modules(self._records_by_id()[plugin_id].import_path)
            return True

    # ── 卸载 ──────────────────────────────────────────────────────────────

    def assert_hot_unloadable(self, name: str | None = None) -> None:
        """Reject an unsafe closure before releasing any accepted resources."""
        records = self._records_for_ids(self.active_plugin_ids)
        if name is not None:
            record = self._find_record(name)
            records = (
                self._records_for_ids(
                    self._kernel.closure(record.manifest.id, optional=False)
                )
                if record and record.manifest.id in self.active_plugin_ids
                else []
            )
        if unsafe := hot_unload_blockers(records):
            raise PluginRestartRequired(unsafe)

    def _enable_closure(self, target: PluginView) -> list[PluginView]:
        """Include blocked dependents and running optional consumers of an enable."""
        records = self._records_by_id()
        for dependency in target.record.manifest.dependencies:
            record = records.get(dependency)
            if record is not None and self._view(record).state not in {
                "ACTIVE",
                "DISABLED",
            }:
                raise PluginReloadUnsupported([dependency], "failed")
        blocked = [
            view.plugin_id
            for view in self.views()
            if view.state == "BLOCKED" and view.record.admission is None
        ]
        return [
            self._view(record)
            for record in self._records_for_ids(
                self._kernel.closure(
                    target.plugin_id,
                    optional=True,
                    among=[*blocked, *self.active_plugin_ids],
                )
            )
        ]

    def _disable_closure(self, target: PluginView) -> list[PluginView] | None:
        if target.state == "ACTIVE":
            return [
                self._view(record)
                for record in self._records_for_ids(
                    self._kernel.closure(target.plugin_id, optional=True)
                )
            ]
        if target.state == "RESTART_REQUIRED":
            raise PluginReloadUnsupported([target.plugin_id], "failed")
        if target.record.admission is None and target.state in {"FAILED", "BLOCKED"}:
            return [target]
        return None

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
            record = self._find_record(name)
            if record is None:
                raise LookupError(f"未找到插件: {name}")
            closure = self._reload_closure(record)
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

    def _reload_closure(self, record: PluginRecord) -> list[PluginView]:
        if self._retired:
            raise PluginReloadUnsupported([record.manifest.id], "retired")
        target = self._view(record)
        if target.state != "ACTIVE":
            raise PluginReloadUnsupported(
                [target.plugin_id],
                "disabled" if target.state == "DISABLED" else "failed",
            )
        members = self._kernel.closure(target.plugin_id, optional=True)
        if refusal := self._kernel.restart_only(members):
            raise _restart_only(refusal) from refusal
        return [self._view(item) for item in self._records_for_ids(members)]

    def _refuse_restart_only(self, closure: list[PluginView]) -> None:
        if refusal := self._kernel.restart_only(view.plugin_id for view in closure):
            raise _restart_only(refusal)

    def _records_for_ids(self, plugin_ids: Iterable[str]) -> list[PluginRecord]:
        records = self._records_by_id()
        return [records[plugin_id] for plugin_id in plugin_ids]

    def _reload_steps(self, *, disabled: frozenset[str] = frozenset()) -> ReloadSteps:
        async def dispose(record: PluginRecord) -> list[Exception]:
            plugin_id = record.manifest.id
            self._rpc.communication.remove_plugin(
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
            drain=self._drain_closure,
            dispose=dispose,
            activate=self._activate_reloaded,
            retain=self._retain_process_resources,
            calls=calls,
        )

    async def _drain_closure(self, closure: list[PluginRecord], timeout: float) -> None:
        """Seal one dependent at a time; an abandoned drain reopens every old gate."""
        gates = {
            record.manifest.id: self._instances[record.manifest.id].calls
            for record in closure
        }

        async def seal(plugin_id: str) -> None:
            gates[plugin_id].seal()
            await gates[plugin_id].wait_idle()

        try:
            await self._kernel.drain(list(gates), timeout, seal)
        except BaseException as error:
            for gate in gates.values():
                gate.reopen()
            if isinstance(error, KernelError):
                raise PluginReloadTimeout(error.plugin_ids, timeout) from error
            raise

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
            record = self._find_record(name)
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
                    self._enable_closure(target)
                    if target.state == "DISABLED" or target.diagnostic == NOT_STARTED
                    else None
                )
            else:
                closure = self._disable_closure(target)
            if closure is None:
                previous = tables.swap(plugin_id, values, raw_values)
                try:
                    if commit is not None:
                        commit(())
                except BaseException:
                    _ = tables.swap(plugin_id, *previous)
                    raise
                return PluginReloadResult((), ())
            self._refuse_restart_only(closure)
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
        _purge_modules(record.import_path)
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
        if plugin_id in self.active_plugin_ids:
            api = self._kernel.get(plugin_key(plugin_id))
            if api is None and not optional:
                raise PluginDependencyError(f"插件 {plugin_id} 未导出接口")
            return api
        if optional:
            return None
        raise PluginDependencyError(f"插件 {plugin_id} 不可用")

    async def drain(self) -> None:
        """Wait for accepted work while the retiring transport is still attached."""
        async with self._transition_lock:
            for plugin_id in reversed(self.active_plugin_ids):
                await self._kernel.scope(plugin_id).drain()

    # ── 聚合面（供宿主接线） ────────────────

    def _view(self, record: PluginRecord) -> PluginView:
        return plugin_view(
            record,
            self._config_enabled(record.manifest),
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
        record = self._find_record(name)
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


def _import_module(module_name: str, path: Path, loader: Loader | None = None) -> None:
    # 把入口文件当成包加载，允许插件内部相对 import；先入 sys.modules 再执行
    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
        loader=loader,
        submodule_search_locations=[str(path.parent)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载插件文件: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)


def _purge_modules(import_path: str) -> None:
    for module_name in tuple(sys.modules):
        if module_name == import_path or module_name.startswith(import_path + "."):
            _ = sys.modules.pop(module_name, None)


def _restart_only(error: KernelError) -> PluginReloadUnsupported:
    """Maps the kernel's restart-only refusal to the host's reload error."""
    assert error.diagnostic.code == "restart_required", error
    reason = "channels" if error.diagnostic.field == "channels" else "hot_unload"
    return PluginReloadUnsupported(list(error.plugin_ids), reason)


def _declares_channels(record: PluginRecord) -> bool:
    """Whether a plugin declares channels, which only a restart may change (D14)."""
    return bool(record.manifest.channels)


def _required_renderer_kinds(record: PluginRecord) -> frozenset[str]:
    """Returns the manifest's declared renderer kinds that gate ACTIVE display."""
    frontend = record.manifest.metadata.get("frontend", {})
    if isinstance(frontend, dict) and "exports" in frontend:
        return frozenset(
            kind for kind in _RENDERER_GATED_KINDS if kind in frontend["exports"]
        )
    return frozenset()
