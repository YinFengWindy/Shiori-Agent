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
from agent.plugin_host.kv import PluginKVStore
from agent.plugin_host.storage import PluginStorage
from agent.plugin_host.core_keys import (
    HOST_BRIDGE,
    HOST_CONFIG_REFERENCES,
    CoreModule,
    PluginBinding,
    bind_core_capabilities,
    required_core_key,
)
from agent.plugin_host.config_schema import (
    PluginConfigSchemaRegistry,
    resolve_config_model,
)
from agent.plugin_host.dependencies import PluginDependencies, PluginDependencyError
from agent.plugin_host.discovery import (
    ExternalSourceDiagnostic,
    discover_plugins,
    find_uninstalled_external_sources,
    refresh_dependency_admission,
)
from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.handle import PluginHandle, PluginRecord, PluginState
from agent.plugin_host.host_contract import HostRuntimeContract
from agent.plugin_host.manifest import (
    ManifestError,
    PluginManifest,
)
from agent.plugin_host.package_fingerprint import (
    PackageContent,
    inspect_package_content,
)
from agent.plugin_host.plugin_data import (
    open_plugin_kv,
)
from agent.plugin_host.runtime_context import PluginRuntimeContext, PluginSetupContext
from agent.plugin_host.runtime_lifecycle import PluginRuntimeLifecycle
from agent.plugin_host.trust_store import PluginTrustStore
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
    PluginStatus,
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

# Diagnostic codes ``Kernel.plan`` gives a plugin it excludes before any setup.
_PLAN_EXCLUSIONS = frozenset(
    {"replaced", "conflict", "duplicate_provider", "dependency_cycle"}
)

# Host-handle states a later load must not overwrite or activate again.
_SETTLED_HANDLE_STATES = frozenset(
    {
        PluginState.ACTIVE,
        PluginState.DISABLED,
        PluginState.BLOCKED,
        PluginState.CONFLICT,
        PluginState.UNTRUSTED,
    }
)

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

    # Trust store, execution identity and plugin KV root; None in host tests
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
    # Frozen hosts may supply their build's dependency inventory and renderer ABI.
    plugin_runtime_contract: HostRuntimeContract | None = None


class PluginKernel:
    """宿主装配层：发现、准入、信任与 capability 注入，生命周期交给 ``shiori_sdk.kernel``。

    每个插件句柄对应内核里的一个 ``PluginSpec``。激活走 ``Kernel.start``：
    内核只 setup 可运行且尚未运行的 spec。指纹与执行身份在 plan 之前复核，被拒的
    插件只登记，不进 ``start``；spec 的 setup 只用复核过的那份内容导入，并兜底
    拒绝未经宿主准备的启动。``runnable`` 表示宿主本轮打算运行：失败、依赖阻塞、
    已卸载的插件都重新 plan 成只登记，``start`` 不会顺带重跑它们。
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
        self._handles: dict[str, PluginHandle] = {}
        # Screened package content per candidate id, from the check before the
        # plan until the spec setup imports exactly these verified bytes.
        self._contents: dict[str, PackageContent | None] = {}
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
        """Reads active dependency declarations from the existing lifecycle owner."""
        for handle in self._handles.values():
            if (
                handle.plugin_id == plugin_id
                and handle.state is PluginState.ACTIVE
                and handle.effects.active
            ):
                manifest = handle.record.manifest
                return (*manifest.dependencies, *manifest.optional_dependencies)
        return None

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
            host=self._settings.plugin_runtime_contract,
            trust=(
                PluginTrustStore(self._settings.workspace)
                if self._settings.workspace is not None
                else None
            ),
        )

    async def admit_trusted_candidate(self, candidate: PluginRecord) -> None:
        """Admit only one verified startup candidate; execution stays in normal loading."""
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
            handle = self._handles.get(candidate.candidate_id)
            if handle is not None and handle.state not in {
                PluginState.UNTRUSTED,
                PluginState.BLOCKED,
                PluginState.DISABLED,
            }:
                raise ValueError("插件已执行或状态已变化，请重新读取后操作")
            records = self.discover()
            previous_admissions = {
                record.candidate_id: record.admission for record in records
            }
            records[records.index(previous)] = candidate
            workspace = self._settings.workspace
            if workspace is None:
                raise ValueError("插件工作区不可用")
            refresh_dependency_admission(records, PluginTrustStore(workspace))
            self._records = records
            for record in records:
                target = record.candidate_id == candidate.candidate_id
                if (
                    not target
                    and record.admission == previous_admissions[record.candidate_id]
                ):
                    continue
                current = self._handles.get(record.candidate_id)
                if current is not None and current.state in {
                    PluginState.UNTRUSTED,
                    PluginState.BLOCKED,
                    PluginState.DISABLED,
                }:
                    current.record = record
                    if target:
                        current.error = None
                        current.state = PluginState.DISABLED
                    elif record.admission is not None:
                        current.error = RuntimeError(record.admission.reason)
                        current.state = PluginState[record.admission.state]
                    # Clearing static admission does not disable a waiting consumer.
                    # Keep its runtime BLOCKED state/cause so the normal enable
                    # closure can recover it when its approved provider starts.

    async def fail_admission_activation(
        self, candidate_id: str, fingerprint: str, error: Exception
    ) -> None:
        """Keep a saved grant distinct from a first activation that could not publish."""
        async with self._transition_lock:
            handle = self._handles.get(candidate_id)
            if (
                handle is None
                or handle.record.fingerprint != fingerprint
                or handle.record.admission is not None
                or handle.state is not PluginState.DISABLED
            ):
                return
            handle.error = error
            handle.state = (
                PluginState.RESTART_REQUIRED
                if getattr(error, "code", "") == "plugin_restart_required"
                else PluginState.FAILED
            )

    def uninstalled_external_sources(self) -> list[ExternalSourceDiagnostic]:
        """Display-only reports for external sources this generation did not discover."""
        return find_uninstalled_external_sources(
            self._dirs, external_roots=self._external_dirs, discovered=self.discover()
        )

    # ── 加载 ──────────────────────────────────────────────────────────────

    async def load_all(self) -> None:
        """Plans every discovered plugin and starts the runnable ones.

        Publishing accounts and process resources is the app's job, when this
        generation becomes the running one — not part of loading.
        """
        await self._load_records(self.discover())

    @property
    def namespace(self) -> str:
        """Generation id the process-resource owner publishes and retains under."""
        return self._namespace

    def _records_by_id(self) -> dict[str, PluginRecord]:
        # Conflicts remain visible as separate handles, but cannot be resolved
        # as dependencies or loaded by choosing a preferred directory.
        return {
            record.manifest.id: record
            for record in self.discover()
            if record.admission is None or record.admission.state != "CONFLICT"
        }

    async def _load_records(
        self,
        wanted: list[PluginRecord],
        reactivating: frozenset[str] = frozenset(),
    ) -> None:
        """Loads ``wanted`` plus the enabled hard dependencies they pull in.

        Runnable records (admitted and enabled) are planned, then
        ``Kernel.start`` sets them up in kernel order: dependency depth, then
        plugin id (§8.1). A disabled plugin never loads its dependencies as a
        side effect; a dependency cycle blocks its members before any setup
        (§8.5). ``reactivating`` names plugins brought back by an in-generation
        reload; their setup sees ``was_active`` and ``is_reload`` as True.
        Re-planning also loads the runnable plugins a plan exclusion had
        blocked and the new plan admits (see ``_lifted_exclusions``).

        Fingerprint and execution identity are checked before the plan, so a
        refused package is register-only and excludes no one: a duplicate
        provider of the same key, say, starts in this same round. A selected
        plugin this round does not start is re-planned register-only; a
        failed or blocked one is retried only when a later round selects it.
        """
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
                    records[dependency]
                    for dependency in record.manifest.dependencies
                    if dependency in records
                )
        activate: dict[str, PluginRecord] = {}
        try:
            for record in selected.values():
                if self._wants_start(record):
                    _ = self._screen(record)
            # Disabled and admission-failed plugins (including the ones just
            # refused) are planned as register-only. Only conflicting
            # candidates stay out of the plan: their id is ambiguous. They
            # still get handles so the Plugins page can show the conflict.
            order = await self._kernel.plan(
                self._spec(record)
                for record in selected.values()
                if records.get(record.manifest.id) is record
            )
            planned = set(order)
            for record in selected.values():
                if not self._runnable(record):
                    self._materialize_inactive(record)
                elif record.manifest.id not in planned:
                    self._block_excluded(record)
            for record in selected.values():
                if self._wants_start(record) and record.manifest.id in planned:
                    activate[record.manifest.id] = record
            activate.update(await self._admit_lifted(order))
            # Planned runnable above, but not started now: a dependency-BLOCKED
            # one, say, must not be run by this or a later ``start``.
            await self._park(
                record
                for record in selected.values()
                if record.manifest.id in planned
                and record.manifest.id not in activate
                and records.get(record.manifest.id) is record
                and self._runnable(record)
                and not self._running(record.manifest.id)
            )
            await self._start_plugins(activate, reactivating)
        finally:
            for record in (*selected.values(), *activate.values()):
                _ = self._contents.pop(record.candidate_id, None)

    def _runnable(self, record: PluginRecord) -> bool:
        return record.admission is None and self._config_enabled(record.manifest)

    def _wants_start(self, record: PluginRecord) -> bool:
        """Whether a round selecting ``record`` should start it, if planned.

        Not yet loaded, FAILED, RESTART_REQUIRED or disposed: yes, a selection
        is an explicit retry. Running, disabled, BLOCKED and the like: no.
        """
        if not self._runnable(record):
            return False
        existing = self._handles.get(record.candidate_id)
        return existing is None or existing.state not in _SETTLED_HANDLE_STATES

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
            self._contents[record.candidate_id] = None
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
        self._contents[record.candidate_id] = content
        return True

    async def _admit_lifted(self, order: Sequence[str]) -> dict[str, PluginRecord]:
        """Screens the plugins ``_lifted_exclusions`` releases; returns those to start.

        A refused one is re-planned register-only, which may release another.
        """
        admitted: dict[str, PluginRecord] = {}
        lifted = self._lifted_exclusions(order)
        while lifted:
            refused: list[PluginRecord] = []
            for plugin_id, record in lifted.items():
                if self._screen(record):
                    admitted[plugin_id] = record
                else:
                    refused.append(record)
            if not refused:
                break
            for record in refused:
                self._materialize_inactive(record)
            order = await self._kernel.plan(self._spec(record) for record in refused)
            lifted = self._lifted_exclusions(order)
        return admitted

    async def _park(self, records: Iterable[PluginRecord]) -> None:
        """Re-plans ``records`` register-only: the host no longer means to run them.

        Keeps ``runnable`` equal to what the host intends, so ``Kernel.start``
        never runs a failed, blocked or disposed plugin as a side effect of
        another plugin's start. A later round that selects one plans it
        runnable again (``_load_records``).
        """
        specs = [replace(self._spec(record), runnable=False) for record in records]
        if specs:
            _ = await self._kernel.plan(specs)

    def _lifted_exclusions(self, order: Sequence[str]) -> dict[str, PluginRecord]:
        """Runnable plugins a plan exclusion BLOCKED that the new plan admits.

        The kernel only settles newly excluded plugins, so one whose conflict,
        replacement, duplicate ``provides`` or cycle partner was disabled keeps
        that status. Its stale handle is dropped for the caller to load it in
        plan order, as a generation swap would.
        """
        planned = set(order)
        lifted: dict[str, PluginRecord] = {}
        for handle in list(self._handles.values()):
            status = self._kernel.status(handle.plugin_id)
            if (
                handle.state is PluginState.BLOCKED
                and handle.plugin_id in planned
                and self._runnable(handle.record)
                and status is not None
                and status.diagnostic is not None
                and status.diagnostic.code in _PLAN_EXCLUSIONS
            ):
                del self._handles[handle.record.candidate_id]
                lifted[handle.plugin_id] = handle.record
        return lifted

    def _block_excluded(self, record: PluginRecord) -> None:
        """Records the kernel's plan exclusion (conflict, replacement, duplicate
        ``provides``, dependency cycle) as a BLOCKED handle."""
        if record.candidate_id in self._handles:
            return
        status = self._kernel.status(record.manifest.id)
        assert status is not None and status.diagnostic is not None
        self._handles[record.candidate_id] = PluginHandle(
            record=record,
            state=PluginState.BLOCKED,
            error=self._dependency_error(record, status.diagnostic),
        )

    def _dependency_error(
        self, record: PluginRecord, blocked: PluginDiagnostic
    ) -> PluginDependencyError:
        """Wraps the kernel's BLOCKED diagnostic as the handle's error.

        Package-contract plugins surface it on the Plugins page. The kernel
        names the first unavailable ``requires`` entry ``inject[i]``; the
        adapter's ``requires`` are manifest ``dependencies`` followed by
        ``inject``, so the field is reported under the manifest's own name.
        """
        error = PluginDependencyError(blocked.reason)
        if "package_contract" in record.manifest.metadata:
            error.diagnostic = replace(
                blocked, field=_manifest_requires_field(record.manifest, blocked.field)
            )
        return error

    def _spec(self, record: PluginRecord) -> PluginSpec:
        """Adapts one record to a kernel spec whose setup is the v2 setup.

        Admission-failed and disabled records are register-only (``runnable``
        false), so ``Kernel.start`` will not run them; callers make a spec
        register-only too while the host does not mean to run it (``_park``).
        ``setup`` still refuses a start the host did not prepare (see
        ``_prepared``), so a stray ``Kernel.start`` cannot import unscreened
        code.
        """
        manifest = record.manifest

        async def setup(ctx: Context) -> None:
            handle, content = self._prepared(record)
            try:
                self._record_execution(record, content)
                handle.effects = self._kernel.scope(manifest.id)
                handle.effects.subscribe(
                    lambda: self._rpc.communication.remove_plugin(manifest.id),
                    "renderer-communication",
                )
                self._import_entry(handle, content)
                self._register_config_schema(handle)
                await self._setup_v2(handle, ctx, reactivated=handle.reactivated)
                ctx.provide(plugin_key(manifest.id), handle.instance)
                self._mark_renderer_pending(handle)
                # ACTIVE before ``start`` moves on, so a later plugin's setup
                # can call this one. A failure above leaves the handle LOADING
                # and ``_sync_handles`` rolls it back.
                handle.state = PluginState.ACTIVE
                logger.info("插件已加载: %s", handle.record.name)
            except BaseException:
                # A rolled-back instance never admits calls again, even via
                # stale references; the kernel then releases its scope.
                handle.calls.retire()
                raise

        # ``requires`` lists ``manifest.dependencies`` first, then ``inject``,
        # each in manifest order: ``_dependency_error`` maps the kernel's
        # ``inject[i]`` field back to the manifest entry by that order.
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

    async def load(self, name: str) -> bool:
        """Load one unique name/ID or exact candidate ID; admission is never bypassed."""
        record = self._find_record(name)
        if record is None:
            return False
        async with self._transition_lock:
            await self._load_records([record])
        handle = self._handles.get(record.candidate_id)
        return handle is not None and handle.state is PluginState.ACTIVE

    def _materialize_inactive(self, record: PluginRecord) -> None:
        """Records a register-only plugin without entering ``Kernel.start``."""
        existing = self._handles.get(record.candidate_id)
        if existing is not None and existing.state in _SETTLED_HANDLE_STATES:
            return
        if record.admission is not None:
            self._handles[record.candidate_id] = PluginHandle(
                record=record,
                state=PluginState[record.admission.state],
                error=RuntimeError(record.admission.reason),
            )
            return
        self._handles[record.candidate_id] = PluginHandle(
            record=record,
            calls=PluginCallGate(record.manifest.id),
            state=PluginState.DISABLED,
        )
        logger.info("插件已禁用（配置状态）: %s", record.name)

    async def _start_plugins(
        self,
        activate: Mapping[str, PluginRecord],
        reactivating: frozenset[str],
    ) -> None:
        """Runs ``Kernel.start`` for ``activate`` and mirrors the result on handles.

        Every runnable spec without a scope is in ``activate``: the host parks
        whatever else it does not mean to run, so ``start`` runs exactly these.
        The ones that do not become ACTIVE are parked afterwards.
        """
        if not activate:
            return
        # Handles must exist before setup. Insert them in kernel order so
        # ``states()`` stays dependency order, then plugin id.
        previous: dict[str, PluginHandle | None] = {}
        for plugin_id in self._kernel.order():
            record = activate.get(plugin_id)
            if record is not None:
                previous[plugin_id] = self._handles.get(record.candidate_id)
                self._handles[record.candidate_id] = PluginHandle(
                    record=record,
                    calls=PluginCallGate(record.manifest.id),
                    reactivated=plugin_id in reactivating,
                    state=PluginState.LOADING,
                )
        before = {plugin_id: self._kernel.status(plugin_id) for plugin_id in activate}
        try:
            await self._kernel.start(self._spec(record) for record in activate.values())
        except BaseException:
            # Cancellation: roll the handles back synchronously first, so they
            # are right even if parking is interrupted too, then propagate.
            await self._park(self._sync_handles(activate, before, previous))
            raise
        await self._park(self._sync_handles(activate, before, previous))

    def _running(self, plugin_id: str) -> bool:
        """Whether the kernel currently holds ``plugin_id``'s scope."""
        try:
            _ = self._kernel.scope(plugin_id)
        except KeyError:
            return False
        return True

    def _prepared(
        self, record: PluginRecord
    ) -> tuple[PluginHandle, PackageContent | None]:
        """The LOADING handle and screened content of a start the host prepared.

        A backstop: the host only lets ``Kernel.start`` run plugins it gave a
        LOADING handle and screened (``_load_records``). Anything else raises
        with the reason, before any plugin code is imported.
        """
        handle = self._handles.get(record.candidate_id)
        plugin_id = record.manifest.id
        if (
            handle is None
            or handle.record is not record
            or handle.state is not PluginState.LOADING
        ):
            raise _ActivationRefused(f"插件 {plugin_id} 未经宿主准备，不能启动")
        if not self._config_enabled(record.manifest):
            raise _ActivationRefused(f"插件 {plugin_id} 已禁用，不能启动")
        if record.candidate_id not in self._contents:
            raise _ActivationRefused(f"插件 {plugin_id} 的包内容未经复核，不能启动")
        return handle, self._contents.pop(record.candidate_id)

    def _record_execution(
        self, record: PluginRecord, content: PackageContent | None
    ) -> None:
        """Persists the execution identity of screened workspace content, before import."""
        if content is not None and self._settings.workspace is not None:
            PluginExecutionIdentity(self._settings.workspace).record(
                record.manifest.id, record.plugin_dir, content.fingerprint
            )

    def _mark_renderer_pending(self, handle: PluginHandle) -> None:
        """Marks renderer kinds still to confirm, and mints this attempt's token.

        Backend contributions are already live once setup returns. The token
        is what ``plugins.activation.report`` echoes so a late report cannot
        attach to a newer handle of the same plugin id.
        """
        handle.pending_renderer_kinds = _required_renderer_kinds(handle.record)
        handle.activation_token = uuid4().hex

    def _sync_handles(
        self,
        activate: Mapping[str, PluginRecord],
        before: Mapping[str, PluginStatus | None],
        previous: Mapping[str, PluginHandle | None],
    ) -> list[PluginRecord]:
        """Copies kernel status onto host handles; returns the ones not ACTIVE.

        One plugin's setup failure does not abort the sweep (#262): the kernel
        has already released its scope, and the handle becomes ``FAILED`` or
        ``RESTART_REQUIRED``. A plugin ``start`` never reached (it was
        cancelled first) gets back the handle it had before, or none; one
        whose release was interrupted keeps its LOADING handle.
        """
        stopped: list[PluginRecord] = []
        for plugin_id, record in activate.items():
            handle = self._handles[record.candidate_id]
            status = self._kernel.status(plugin_id)
            if handle.state is PluginState.ACTIVE:
                continue
            stopped.append(record)
            if status is None or status is before[plugin_id]:
                if self._running(plugin_id):
                    # Cancelled again while releasing: the kernel still holds
                    # the scope, and the LOADING handle lets force cleanup
                    # (``terminate_all``) finish it.
                    continue
                if (earlier := previous[plugin_id]) is None:
                    del self._handles[record.candidate_id]
                else:
                    self._handles[record.candidate_id] = earlier
                continue
            if status.state in {KernelState.BLOCKED, KernelState.REPLACED}:
                handle.state = PluginState.BLOCKED
                assert status.diagnostic is not None
                handle.error = self._dependency_error(record, status.diagnostic)
                continue
            assert status.error is not None
            logger.warning("插件 %s 加载失败，回滚: %s", record.name, status.error)
            self._after_rollback(handle, status.error, status.cleanup_errors)
        return stopped

    def _config_enabled(self, manifest: PluginManifest) -> bool:
        """Reads the authoritative enable flag; absent falls back to the manifest."""
        return plugin_enabled(
            manifest, self._settings.plugin_configs.get(manifest.id, {})
        )

    def _import_entry(
        self, handle: PluginHandle, content: PackageContent | None = None
    ) -> None:
        record = handle.record
        # 先登记命名空间清理（最后处置），代际热重载时不残留 sys.modules 条目。
        # 入口及其相对导入的子模块都挂在这个动态包下，必须整体清理。
        if content is None:
            _import_module(record.import_path, record.entry_file)
        else:
            imports = TrustedPluginImports(record.import_path, content.sources)
            imports.install()
            _ = handle.effects.effect(imports.remove, "trusted-source-imports")
            _import_module(
                record.import_path,
                record.entry_file,
                imports.loader(record.import_path, record.entry_file),
            )

    def _register_config_schema(self, handle: PluginHandle) -> None:
        """Registers the manifest configuration model, tied to the handle's own lifetime.

        Deliberately NOT a setup-rollback effect: a plugin whose ``setup()``
        raises *because* its stored config is invalid (e.g. a value that now
        fails a manifest-declared model constraint) must stay repairable
        through ``plugin.config.set`` while FAILED — see
        ``_rollback_failed_load``/``_dispose_handle`` for the corresponding
        unregister. Registering it as a rollback effect would unregister the
        schema the instant setup fails, turning ``plugin.config.set`` into
        ``plugin_config_unsupported`` and leaving the value fixable only by
        hand-editing the TOML file directly.
        """
        model_cls = resolve_config_model(handle.record)
        if model_cls is None:
            return
        self.config_schemas.register(handle.plugin_id, model_cls)

    async def _setup_v2(
        self, handle: PluginHandle, kernel_context: Context, *, reactivated: bool
    ) -> None:
        module = sys.modules[handle.record.import_path]
        setup = getattr(module, "setup", None)
        if not callable(setup):
            raise ManifestError(
                f"v2 插件 {handle.record.name} 的入口缺少 setup(ctx) 函数"
            )
        setup_fn = cast("Callable[[SdkRuntimeContext], Awaitable[None]]", setup)
        manifest = handle.record.manifest
        grants = manifest.capabilities
        # Built for the names in either inject list, like config (P4-3).
        injected = {*manifest.inject, *manifest.optional_inject}
        settings = self._settings
        binding = PluginBinding(
            plugin_id=handle.plugin_id,
            namespace=self._namespace,
            manifest=manifest,
            scope=handle.effects,
            calls=handle.calls,
        )
        core_capabilities = bind_core_capabilities(grants, self._kernel.get, binding)
        context: PluginSetupContext = PluginRuntimeContext(
            plugin_id=handle.plugin_id,
            plugin_dir=handle.record.plugin_dir,
            manifest=manifest,
            effects=handle.effects,
            config=PluginConfig(
                self._settings.plugin_configs.get(handle.plugin_id, {}),
                resolve_reference=self._resolve_reference,
                raw_values=self._settings.raw_plugin_configs.get(handle.plugin_id),
            ),
            dependencies=PluginDependencies(
                manifest.dependencies,
                self._dependency_api,
                optional_declared=manifest.optional_dependencies,
            ),
            storage=PluginStorage(),
            kv=(
                self._open_kv(handle.plugin_id)
                if "kv" in grants or "kv" in injected
                else None
            ),
            runtime=PluginRuntimeLifecycle(
                settings.is_reload or reactivated,
                handle.effects.drainers,
                was_active=reactivated
                or handle.plugin_id in settings.previously_active_plugins,
            ),
            services=(
                ScopedPluginServices(
                    self._rpc.services, handle.plugin_id, handle.effects, handle.calls
                )
                if "services" in grants or "services" in injected
                else None
            ),
            publish_api=lambda api: setattr(handle, "instance", api),
            kernel_context=kernel_context,
            binding=binding,
            **core_capabilities,
        )
        context.as_service_provider_context()
        context.as_hook_context()
        context.as_command_context()
        context.as_observe_context()
        context.as_service_context()
        context.as_channel_context()
        await setup_fn(
            context.as_memory_context()
            if "memory" in handle.record.manifest.capabilities
            else context.as_sdk_context()
        )

    def _open_kv(self, plugin_id: str) -> PluginKVStore:
        """The plugin's KV store under the generation's workspace (``kv``).

        Without a workspace a plugin declaring ``kv`` fails before setup rather
        than falling back to its package directory (#209).
        """
        workspace = self._settings.workspace
        if workspace is None:
            raise HostServiceUnavailable.for_capability(plugin_id, "kv", ["workspace"])
        return open_plugin_kv(workspace=workspace, plugin_id=plugin_id)

    async def _rollback_failed_load(
        self, handle: PluginHandle, error: BaseException
    ) -> None:
        """Rolls an ACTIVE plugin back to FAILED through the kernel (renderer failure)."""
        logger.warning("插件 %s 加载失败，回滚: %s", handle.record.name, error)
        # A rolled-back instance never admits calls again, even via stale references.
        handle.calls.retire()
        cleanup_errors = await self._kernel.deactivate(handle.plugin_id)
        self._after_rollback(handle, error, cleanup_errors)
        # Retried only when a later round selects it, like a setup failure.
        await self._park([handle.record])

    def _after_rollback(
        self,
        handle: PluginHandle,
        error: BaseException,
        cleanup_errors: tuple[Exception, ...] | list[Exception],
    ) -> None:
        """Host bookkeeping once the kernel released a failed instance's scope."""
        _purge_modules(handle.record.import_path)
        handle.instance = None
        handle.pending_renderer_kinds = frozenset()
        handle.activation_token = ""
        # A rollback that could not fully dispose its own effects cannot
        # guarantee a clean slate for an immediate retry; RESTART_REQUIRED
        # marks that distinctly from a plain FAILED (#262 AC6 — "验证停用后
        # 所有资源均释放").
        handle.state = (
            PluginState.RESTART_REQUIRED if cleanup_errors else PluginState.FAILED
        )
        handle.error = error

    # ── 渲染入口激活汇总（#262） ────────────────────────────────────────────

    def _find_active_handle(
        self, plugin_id: str, activation_token: str
    ) -> PluginHandle | None:
        """Returns the current generation's ACTIVE handle for ``plugin_id``, if any.

        Used by both ``confirm_renderer_entry`` and ``fail_renderer_entry``:
        a report naming a plugin this kernel does not currently consider
        ACTIVE (already FAILED, disabled, or belonging to a superseded
        generation) is stale and must be ignored rather than raising, since a
        renderer process cannot synchronously know the backend's current view.

        ``activation_token`` closes a narrower race than plugin identity
        alone can: disable-then-re-enable the *same* plugin id replaces this
        handle with a fresh one (a new ``PluginKernel``/generation, see
        ``bootstrap/tools.py``), but a renderer's abandoned load attempt from
        the discarded handle can still resolve and report late. Matching
        plugin id is not enough to reject that report — the id is identical —
        so every ACTIVE handle mints a fresh ``activation_token`` (see
        ``_mark_renderer_pending``) that the renderer must echo back; a mismatch is
        treated exactly like "plugin not found".
        """
        for handle in self._handles.values():
            if (
                handle.plugin_id == plugin_id
                and handle.state is PluginState.ACTIVE
                and handle.activation_token == activation_token
            ):
                return handle
        return None

    async def confirm_renderer_entry(
        self, plugin_id: str, kind: str, activation_token: str
    ) -> bool:
        """Marks one required renderer kind ready; idempotent and order-free.

        Backend contributions are already live once ``setup()`` returns (see
        ``_load_one``); this only shrinks ``pending_renderer_kinds`` so the
        Plugins page stops showing the plugin as still activating once every
        declared ``ui``/``background`` entry has confirmed. Returns whether
        this call actually changed anything, so callers can skip a no-op
        broadcast for a duplicate, unrequired, or stale-generation confirmation.
        """
        handle = self._find_active_handle(plugin_id, activation_token)
        if handle is None or kind not in handle.pending_renderer_kinds:
            return False
        handle.pending_renderer_kinds = handle.pending_renderer_kinds - {kind}
        if not handle.pending_renderer_kinds:
            logger.info("插件渲染入口全部就绪: %s", handle.record.name)
        return True

    async def fail_renderer_entry(
        self, plugin_id: str, kind: str, reason: str, activation_token: str
    ) -> bool:
        """Rolls back an ACTIVE plugin whose renderer entry failed to load.

        Any declared kind can trigger this, including ``surface`` — it is
        not part of ``pending_renderer_kinds`` (see ``_RENDERER_GATED_KINDS``)
        but a surface that fails after the plugin is already displayed ACTIVE
        must still tear down every other contribution (#262 AC2). Reuses the
        exact same rollback core as a setup-time failure so cleanup, module
        purge and the FAILED/RESTART_REQUIRED distinction are not
        reimplemented here.
        """
        handle = self._find_active_handle(plugin_id, activation_token)
        if handle is None:
            return False
        diagnostic = PluginDiagnostic(
            code=f"renderer_{kind}_failed",
            stage=kind,
            field=f"renderer.{kind}.entry",
            reason=reason,
            state="FAILED",
        )
        await self._rollback_failed_load(handle, RendererActivationError(diagnostic))
        return True

    # ── 卸载 ──────────────────────────────────────────────────────────────

    def assert_hot_unloadable(self, name: str | None = None) -> None:
        """Preflights the whole strong-dependent closure before any disposal."""
        handles = (
            self._unload_closure(name) if name is not None else self._active_handles()
        )
        if unsafe := hot_unload_blockers(handles):
            raise PluginRestartRequired(unsafe)

    def _unload_closure(self, name: str) -> list[PluginHandle]:
        record = self._find_record(name)
        handle = self._handles.get(record.candidate_id) if record else None
        if handle is None or handle.state is not PluginState.ACTIVE:
            return []
        return self._handles_by_id(
            self._kernel.closure(handle.plugin_id, optional=False)
        )

    def _enable_closure(self, target: PluginHandle) -> list[PluginHandle]:
        """A DISABLED target plus the plugins its absence blocks, dependents first.

        Its hard dependencies are not loaded with it: a DISABLED one leaves the
        target BLOCKED, as a generation swap would, while one in any other
        inactive state could only be retried by a swap, which is required then.
        """
        records = self._records_by_id()
        for dependency in target.record.manifest.dependencies:
            record = records.get(dependency)
            handle = self._handles.get(record.candidate_id) if record else None
            if handle is not None and handle.state not in {
                PluginState.ACTIVE,
                PluginState.DISABLED,
            }:
                raise PluginReloadUnsupported([dependency], "failed")
        blocked = [
            handle.plugin_id
            for handle in self._handles.values()
            if handle.state is PluginState.BLOCKED and handle.record.admission is None
        ]
        return self._handles_by_id(
            self._kernel.closure(target.plugin_id, optional=False, among=blocked)
        )

    def _disable_closure(self, target: PluginHandle) -> list[PluginHandle] | None:
        """Handles to unload when disabling ``target``; None when its state stays."""
        if target.state is PluginState.ACTIVE:
            return self._handles_by_id(
                self._kernel.closure(target.plugin_id, optional=False)
            )
        if target.record.admission is None and target.state in {
            PluginState.FAILED,
            PluginState.BLOCKED,
        }:
            # Nothing runs; the handle only becomes DISABLED.
            return [target]
        if target.state is PluginState.RESTART_REQUIRED:
            raise PluginReloadUnsupported([target.plugin_id], "failed")
        return None

    async def unload(self, name: str, *, force: bool = False) -> list[Exception]:
        """Disposes a dependency closure; force is reserved for final resource cleanup."""
        async with self._transition_lock:
            return await self._unload(name, force=force)

    async def _unload(self, name: str, *, force: bool) -> list[Exception]:
        closure = self._unload_closure(name)
        if not force:
            self.assert_hot_unloadable(name)
        errors: list[Exception] = []
        for handle in closure:
            errors.extend(await self._dispose_handle(handle))
        return errors

    async def reload(
        self,
        name: str,
        *,
        values: dict[str, Any],
        raw_values: dict[str, Any],
        drain_timeout: float,
        commit: Callable[[tuple[str, ...]], None] | None = None,
    ) -> PluginReloadResult:
        """Re-runs setup of an ACTIVE plugin with new config, within this generation.

        ``values``/``raw_values`` replace the plugin table in
        ``PluginGenerationSettings.plugin_configs``/``raw_plugin_configs`` (the live
        generation config); the enable flag inside them must stay on
        (``ValueError`` otherwise). The closure (target plus ACTIVE plugins
        that hard-depend on it) is sealed, drained within ``drain_timeout``
        seconds and disposed dependents-first, then set up again target-first
        with ``ctx.runtime.was_active``/``is_reload`` True. Plugins outside it
        are untouched; the closure's process resources survive.

        ``commit`` (given the reloaded plugin ids) persists the new config
        once every closure plugin is ACTIVE with it. It runs synchronously in
        the same uninterruptible replacement as the setup, so caller
        cancellation cannot separate "reloaded" from "persisted"; when it
        raises, the reload is rolled back like a setup failure of the target.

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
                closure,
                values=values,
                raw_values=raw_values,
                tables=ConfigTables(
                    self._settings.plugin_configs, self._settings.raw_plugin_configs
                ),
                steps=self._reload_steps(),
                drain_timeout=drain_timeout,
                commit=commit,
            )

    def _reload_closure(self, record: PluginRecord) -> list[PluginHandle]:
        """The kernel's reload set for ``record``, dependents first, or a refusal.

        Besides hard dependents it holds the running plugins that optionally
        inject the target (§8.2). Refused when only a generation swap applies:
        retired generation, inactive target, or a closure member declaring
        channels or ``supports_hot_unload: false`` (D14).
        """
        plugin_id = record.manifest.id
        if self._retired:
            raise PluginReloadUnsupported([plugin_id], "retired")
        target = self._handles.get(record.candidate_id)
        if target is None or target.state is not PluginState.ACTIVE:
            disabled = target is not None and target.state is PluginState.DISABLED
            raise PluginReloadUnsupported(
                [plugin_id], "disabled" if disabled else "failed"
            )
        try:
            members = self._kernel.reload_closure(plugin_id)
        except KernelError as error:
            raise _restart_only(error) from error
        return self._handles_by_id(members)

    def _refuse_restart_only(self, closure: list[PluginHandle]) -> None:
        """Refuses a toggle the kernel says only a restart may apply (D14)."""
        ids = [handle.plugin_id for handle in closure]
        if (refusal := self._kernel.restart_only(ids)) is not None:
            raise _restart_only(refusal) from refusal

    def _handles_by_id(self, plugin_ids: Iterable[str]) -> list[PluginHandle]:
        """The admitted handles of kernel plugin ids, in the given order."""
        by_id = {
            handle.plugin_id: handle
            for handle in self._handles.values()
            if handle.record.admission is None
        }
        return [by_id[plugin_id] for plugin_id in plugin_ids]

    def _reload_steps(self) -> ReloadSteps:
        return ReloadSteps(
            drain=self._drain_closure,
            dispose=self._dispose_handle,
            activate=self._activate_reloaded,
            retain=self._retain_process_resources,
        )

    async def _drain_closure(self, closure: list[PluginHandle], timeout: float) -> None:
        """Drains ``closure`` through the kernel, sealing each call gate first.

        Each stage seals one plugin's gate and waits for its admitted calls,
        then the kernel runs its default drain and ``on_drain``; providers stay
        open meanwhile, so a dependent's accepted work can still call them.
        When the drain is abandoned (timeout, ``on_drain`` failure,
        cancellation) every gate reopens and every instance stays as it was.
        """
        gates = {handle.plugin_id: handle.calls for handle in closure}

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
        - When the plugin's state does not change, only the tables are replaced
          (``plugin_ids`` empty).

        ``commit`` (given the affected plugin ids) persists the change inside
        the same uninterruptible transition; when it raises, the previous tables
        and states are restored and ``PluginReloadFailed`` (or, when nothing was
        loaded or unloaded, the commit error itself) is raised. Raises
        ``PluginReloadUnsupported`` with nothing changed when only a generation
        swap applies: the generation is retired, the closure has channels or
        cannot be hot unloaded, or a plugin involved is in a state only a swap
        can retry. See ``agent.plugin_host.reload.toggle_closure``.
        """
        async with self._transition_lock:
            record = self._find_record(name)
            if record is None:
                raise LookupError(f"未找到插件: {name}")
            plugin_id = record.manifest.id
            if self._retired:
                raise PluginReloadUnsupported([plugin_id], "retired")
            target = self._handles.get(record.candidate_id)
            if target is None:
                raise PluginReloadUnsupported([plugin_id], "failed")
            enabled = plugin_enabled(record.manifest, values)
            tables = ConfigTables(
                self._settings.plugin_configs, self._settings.raw_plugin_configs
            )
            if enabled:
                closure = (
                    self._enable_closure(target)
                    if target.state is PluginState.DISABLED
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
            result = await toggle_closure(
                closure,
                enabled=enabled,
                values=values,
                raw_values=raw_values,
                tables=tables,
                steps=self._reload_steps(),
                drain_timeout=drain_timeout,
                commit=commit,
            )
            if not enabled:
                # A later re-enable within this generation is a fresh start.
                self._settings.previously_active_plugins -= frozenset(result.plugin_ids)
            return result

    async def _activate_reloaded(
        self, record: PluginRecord, reactivating: frozenset[str]
    ) -> PluginHandle | None:
        await self._load_records([record], reactivating)
        return self._handles.get(record.candidate_id)

    def _retain_process_resources(
        self, plugin_ids: tuple[str, ...]
    ) -> ProcessResourceHold | None:
        owner = self._settings.process_resources
        return None if owner is None else owner.retain(self._namespace, plugin_ids)

    async def _dispose_handle(self, handle: PluginHandle) -> list[Exception]:
        # Every disposal path (unload, terminate, reload) stops admitting calls,
        # so stale references to a disposed instance are rejected.
        handle.calls.retire()
        handle.state = PluginState.UNLOADING
        # The kernel releases subscriptions, tasks, then effects LIFO; a
        # failed instance whose release was interrupted finishes here.
        errors = await self._kernel.deactivate(handle.plugin_id)
        # 配置 schema 的生命周期绑定在 handle 本身（真正被卸载/整代被处置时），
        # 不是 setup 回滚 effect 的一部分：见 _register_config_schema 的文档。
        self.config_schemas.unregister(handle.plugin_id)
        _purge_modules(handle.record.import_path)
        handle.instance = None
        handle.state = PluginState.DISPOSED
        self._handles.pop(handle.record.candidate_id, None)
        if handle.record.admission is None:
            # Disposed: no later ``start`` may set it up again unless a round
            # selects it (an in-generation reload or enable does). Last, so a
            # cancelled re-plan cannot skip the synchronous cleanup above.
            await self._park([handle.record])
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
        for name in list(self._active_order):
            errors.extend(await self._unload(name, force=True))
        # Failed/interrupted loads may own effects without an active-order entry.
        for handle in reversed(list(self._handles.values())):
            errors.extend(await self._dispose_handle(handle))
        if errors:
            raise ExceptionGroup("Plugin cleanup failed", errors)

    def _dependency_api(self, plugin_id: str, optional: bool = False) -> Any:
        """The API an ACTIVE plugin provides under its kernel key (``plugin_key``)."""
        if any(handle.plugin_id == plugin_id for handle in self._active_handles()):
            api = self._kernel.get(plugin_key(plugin_id))
            if api is None and not optional:
                raise PluginDependencyError(f"插件 {plugin_id} 未导出接口")
            return api
        if optional:
            return None
        raise PluginDependencyError(f"插件 {plugin_id} 不可用")

    async def drain(self) -> None:
        """Waits for plugin-owned work while the retiring transport remains attached."""
        # Holding the transition lock keeps a reload from interleaving with the
        # retirement drain; no caller re-enters the kernel from on_drain.
        async with self._transition_lock:
            for handle in reversed(self._active_handles()):
                await handle.effects.drain()

    # ── 聚合面（供宿主接线） ────────────────

    @property
    def loaded_count(self) -> int:
        return len(self._active_order)

    @property
    def _active_order(self) -> list[str]:
        """Candidate ids of ACTIVE plugins in kernel order (stable across reloads)."""
        active = [
            handle
            for handle in self._handles.values()
            if handle.state is PluginState.ACTIVE
        ]
        order = {plugin_id: rank for rank, plugin_id in enumerate(self._kernel.order())}
        active.sort(key=lambda handle: order.get(handle.plugin_id, -1))
        return [handle.record.candidate_id for handle in active]

    def states(self) -> list[dict[str, Any]]:
        """Returns per-plugin lifecycle snapshots for diagnostics."""
        return [handle.describe() for handle in self._handles.values()]

    def _active_handles(self) -> list[PluginHandle]:
        return [
            self._handles[name] for name in self._active_order if name in self._handles
        ]

    @property
    def kernel(self) -> Kernel:
        """The generation's kernel, with the core checks; turn events go through it."""
        return self._kernel

    @property
    def active_plugin_ids(self) -> list[str]:
        """Plugin ids of the ACTIVE plugins in kernel order (stable across reloads)."""
        return [handle.plugin_id for handle in self._active_handles()]


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


def _manifest_requires_field(manifest: PluginManifest, field: str) -> str:
    """The manifest entry behind the kernel's ``inject[i]`` field of a ``_spec``."""
    if not field.startswith("inject["):
        return field
    index = int(field.removeprefix("inject[").removesuffix("]"))
    dependencies = len(manifest.dependencies)
    if index < dependencies:
        return f"dependencies[{index}]"
    return f"inject[{index - dependencies}]"


def _restart_only(error: KernelError) -> PluginReloadUnsupported:
    """Maps the kernel's restart-only refusal to the host's reload error."""
    assert error.diagnostic.code == "restart_required", error
    reason = "channels" if error.diagnostic.field == "channels" else "hot_unload"
    return PluginReloadUnsupported(list(error.plugin_ids), reason)


def _declares_channels(record: PluginRecord) -> bool:
    """Whether a plugin declares channels, which only a restart may change (D14)."""
    return "channels" in record.manifest.capabilities or bool(record.manifest.channels)


def _required_renderer_kinds(record: PluginRecord) -> frozenset[str]:
    """Returns the manifest's declared renderer kinds that gate ACTIVE display."""
    renderer = record.manifest.metadata.get("renderer", {})
    if not isinstance(renderer, dict):
        return frozenset()
    return frozenset(kind for kind in _RENDERER_GATED_KINDS if renderer.get(kind))
