"""插件内核：发现、装配、生命周期与失败回滚。

内核只拥有"插件如何被装配、启动、停止和清理"；phase 顺序、事件语义、
工具错误路径等产品语义仍由 Shiori 核心模块定义。
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from agent.plugin_host.capabilities import (
    BackgroundCapability,
    BotCommandsCapability,
    ChannelsCapability,
    LifecycleCapability,
    ProactiveGatesCapability,
    RpcCapability,
    ToolHooksCapability,
    ToolsCapability,
)
from agent.plugin_host.config_schema import (
    PluginConfigSchemaRegistry,
    resolve_config_model,
)
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.dependencies import PluginDependencies, PluginDependencyError
from agent.plugin_host.runtime_lifecycle import PluginRuntimeLifecycle
from agent.plugin_host.events import ScopedEventBus
from agent.plugin_host.handle import PluginHandle, PluginRecord, PluginState
from agent.plugin_host.diagnostics import PackageContractError, PluginDiagnostic
from agent.plugin_host.host_contract import HostRuntimeContract
from agent.plugin_host.package_contract import validate_package
from agent.plugin_host.manifest import (
    ManifestError,
    PluginManifest,
    load_manifest,
)
from agent.plugin_host.plugin_data import (
    open_plugin_kv,
)
from agent.plugin_host.rpc import PluginRpcRegistry
from agent.plugin_host.runtime_context import PluginRuntimeContext
from agent.plugin_host.unload import PluginRestartRequired
from bus.event_bus import EventBus
from core.scene.demand import SceneObservationDemand
from agent.plugin_host.scene_observations import SceneObservationsCapability

logger = logging.getLogger(__name__)

# 启停状态与插件自己的配置同住 [plugins.<id>] 表，但它归宿主所有、不是插件配置
# 模型的字段。凡是整表读写这张表的地方都必须认得这个键，否则会互相覆盖。
PLUGIN_ENABLED_CONFIG_KEY = "enabled"


@dataclass
class HostServices:
    """宿主提供给插件装配的服务集合；capability 只暴露其中被声明的切面。"""

    event_bus: EventBus
    tool_registry: Any = None
    workspace: Path | None = None
    # 宿主唯一的 RoleStore 实例（bootstrap 里的 canonical 那个）。插件经
    # role_store capability 拿到的必须是它本身，见 manifest.KNOWN_CAPABILITIES
    # 里那段注释：另起一个实例就是另起一把写锁。
    role_store: Any = None
    session_manager: Any = None
    memory_engine: Any = None
    app_config: Any = None
    light_provider: Any = None
    light_model: str = ""
    plugin_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    relationship_runtime: Any = None
    # 插件包上移到仓库顶层之前的位置（apps/backend/plugins）。gitignore 覆盖的
    # 本地状态（.kv.json）不会随目录重命名搬走，需要从这里
    # 一次性迁移；打包形态下该目录不存在，字段为 None 即可。
    legacy_plugin_root: Path | None = None
    role_runtime_registry: Any = None
    scene_observations: SceneObservationDemand = field(
        default_factory=SceneObservationDemand
    )
    is_reload: bool = False
    previously_active_plugins: frozenset[str] = frozenset()
    # Frozen hosts may supply their build's dependency inventory and renderer ABI.
    plugin_runtime_contract: HostRuntimeContract | None = None


class PluginKernel:
    """通过作用域 effect 回滚与 capability 注入装配插件，聚合其宿主贡献。"""

    def __init__(
        self,
        plugin_dirs: list[Path],
        *,
        services: HostServices,
        namespace: str = "",
        strict: bool = False,
    ) -> None:
        self._dirs = plugin_dirs
        self._services = services
        self._namespace = namespace
        self._strict = strict
        self._handles: dict[str, PluginHandle] = {}
        self._active_order: list[str] = []
        # 每个内核（= 每个 runtime generation）独立一份 RPC/配置 schema 注册表
        self.rpc = PluginRpcRegistry()
        self.config_schemas = PluginConfigSchemaRegistry()

    # ── 发现 ──────────────────────────────────────────────────────────────

    def discover(self) -> list[PluginRecord]:
        """扫描显式声明 v2 manifest 的插件目录；同名 first-wins。"""
        records: list[PluginRecord] = []
        seen_names: set[str] = set()
        for d in self._dirs:
            if not d.is_dir():
                continue
            source = d.name
            for child in sorted(d.iterdir()):
                if not child.is_dir():
                    continue
                if child.name in seen_names:
                    logger.warning("插件名重复，跳过: %s (%s)", child.name, child)
                    continue
                record = self._build_record(child, source)
                if record is None:
                    continue
                seen_names.add(child.name)
                records.append(record)
        return records

    def _build_record(self, child: Path, source: str) -> PluginRecord | None:
        try:
            manifest = load_manifest(child)
        except ManifestError as e:
            logger.warning("插件 manifest 无效，跳过: %s (%s)", child.name, e)
            if self._strict:
                raise
            if e.metadata is None or "package_contract" not in e.metadata:
                return None
            # Keep invalid contract candidates visible. Static validation reports
            # the original manifest failure before the fallback record can load.
            manifest = PluginManifest(
                id=str(e.metadata.get("id") or child.name), metadata=e.metadata
            )
        if manifest is None:
            return None
        entry_file = child / manifest.entry
        suffix = f"_{self._namespace}" if self._namespace else ""
        return PluginRecord(
            name=child.name,
            plugin_dir=child,
            entry_file=entry_file,
            import_path=f"akasic_plugin_{source}_{child.name}{suffix}",
            manifest=manifest,
        )

    # ── 加载 ──────────────────────────────────────────────────────────────

    async def load_all(self) -> None:
        records = self._records_by_id()
        for record in records.values():
            await self._load_dependencies(record, records, ())

    def _records_by_id(self) -> dict[str, PluginRecord]:
        records: dict[str, PluginRecord] = {}
        for record in self.discover():
            if record.manifest.id in records:
                raise ManifestError(f"插件 ID 重复: {record.manifest.id}")
            records[record.manifest.id] = record
        return records

    async def _load_dependencies(
        self,
        record: PluginRecord,
        records: dict[str, PluginRecord],
        trail: tuple[str, ...],
    ) -> None:
        existing = self._handles.get(record.name)
        if existing is not None and existing.state in {
            PluginState.ACTIVE,
            PluginState.DISABLED,
            PluginState.BLOCKED,
        }:
            return
        plugin_id = record.manifest.id
        if plugin_id in trail:
            raise PluginDependencyError(
                "插件循环依赖: " + " -> ".join((*trail, plugin_id))
            )
        # A disabled plugin must not load its dependencies as a side effect.
        if self._config_enabled(plugin_id):
            for index, dependency in enumerate(record.manifest.dependencies):
                target = records.get(dependency)
                try:
                    if target is None:
                        raise PluginDependencyError(
                            f"插件 {plugin_id} 缺少依赖 {dependency}"
                        )
                    await self._load_dependencies(target, records, (*trail, plugin_id))
                    loaded = self._handles.get(target.name)
                    if loaded is None or loaded.state is not PluginState.ACTIVE:
                        raise PluginDependencyError(
                            f"插件 {plugin_id} 的依赖 {dependency} 未启用或加载失败"
                        )
                except PluginDependencyError as exc:
                    if "package_contract" in record.manifest.metadata:
                        exc.diagnostic = PluginDiagnostic(
                            code=(
                                "missing_dependency"
                                if target is None
                                else "dependency_unavailable"
                            ),
                            stage="dependency",
                            field=f"dependencies[{index}]",
                            reason=str(exc),
                        )
                    self._handles[record.name] = PluginHandle(
                        record=record, state=PluginState.BLOCKED, error=exc
                    )
                    return
        await self._load_one(record)

    async def load(self, name: str) -> bool:
        """按目录名加载单个已发现插件；已激活时幂等返回 True。"""
        records = self._records_by_id()
        for record in records.values():
            if record.name == name:
                await self._load_dependencies(record, records, ())
                handle = self._handles.get(name)
                return handle is not None and handle.state is PluginState.ACTIVE
        return False

    async def _load_one(self, record: PluginRecord) -> None:
        existing = self._handles.get(record.name)
        if existing is not None and existing.state is PluginState.ACTIVE:
            return
        handle = PluginHandle(record=record, effects=EffectScope(record.manifest.id))
        self._handles[record.name] = handle
        if not self._config_enabled(record.manifest.id):
            handle.state = PluginState.DISABLED
            logger.info("插件已禁用（配置状态）: %s", record.name)
            return
        # Check every required contribution before importing any plugin code.
        # Keep this catch outside setup: runtime exceptions must roll back effects.
        if "package_contract" in record.manifest.metadata:
            try:
                _ = validate_package(
                    record.plugin_dir, host=self._services.plugin_runtime_contract
                )
            except PackageContractError as exc:
                handle.state = PluginState.BLOCKED
                handle.error = exc
                if self._strict:
                    raise
                return
        handle.state = PluginState.LOADING
        try:
            self._import_entry(handle)
            self._register_config_schema(handle)
            await self._setup_v2(handle)
        except asyncio.CancelledError as e:
            # A cancelled setup owns registrations even before it becomes ACTIVE.
            await self._rollback_failed_load(handle, e)
            raise
        except Exception as e:
            await self._rollback_failed_load(handle, e)
            if self._strict:
                raise
            return
        handle.state = PluginState.ACTIVE
        self._active_order.append(record.name)
        logger.info("插件已加载: %s", record.name)

    def _config_enabled(self, plugin_id: str) -> bool:
        """Reads the authoritative enable flag; absent means enabled."""
        stored = self._services.plugin_configs.get(plugin_id, {})
        return bool(stored.get(PLUGIN_ENABLED_CONFIG_KEY, True))

    def _import_entry(self, handle: PluginHandle) -> None:
        record = handle.record
        # 先登记命名空间清理（最后处置），代际热重载时不残留 sys.modules 条目
        if self._namespace:
            handle.effects.add(
                "import:namespace",
                lambda: _purge_modules(record.import_path),
            )
        _import_module(record.import_path, record.entry_file)

    def _register_config_schema(self, handle: PluginHandle) -> None:
        """Registers the manifest configuration model with scoped rollback."""
        model_cls = resolve_config_model(handle.record)
        if model_cls is None:
            return
        self.config_schemas.register(handle.plugin_id, model_cls)
        handle.effects.add(
            "config_schema",
            lambda: self.config_schemas.unregister(handle.plugin_id),
        )

    async def _setup_v2(self, handle: PluginHandle) -> None:
        module = sys.modules[handle.record.import_path]
        setup = getattr(module, "setup", None)
        if not callable(setup):
            raise ManifestError(
                f"v2 插件 {handle.record.name} 的入口缺少 setup(ctx) 函数"
            )
        setup_fn = cast("Callable[[PluginRuntimeContext], Awaitable[None]]", setup)
        context = PluginRuntimeContext(
            plugin_id=handle.plugin_id,
            plugin_dir=handle.record.plugin_dir,
            manifest=handle.record.manifest,
            effects=handle.effects,
            capabilities=self._build_capabilities(handle),
            publish_api=lambda api: setattr(handle, "instance", api),
        )
        await setup_fn(context)

    def _build_capabilities(self, handle: PluginHandle) -> dict[str, Any]:
        from agent.plugin_host.config import PluginConfig

        services = self._services
        builders: dict[str, Any] = {
            "scene_observations": lambda: SceneObservationsCapability(
                services.scene_observations, handle.effects
            ),
            "events": lambda: ScopedEventBus(services.event_bus, handle.effects),
            "kv": lambda: open_plugin_kv(
                workspace=services.workspace,
                plugin_id=handle.plugin_id,
                plugin_dir=handle.record.plugin_dir,
                legacy_plugin_root=services.legacy_plugin_root,
            ),
            "config": lambda: PluginConfig(
                services.plugin_configs.get(handle.plugin_id, {})
            ),
            "tools": lambda: ToolsCapability(
                services.tool_registry,
                handle.effects,
                handle.contributions,
                handle.plugin_id,
            ),
            "lifecycle": lambda: LifecycleCapability(
                handle.contributions, handle.effects
            ),
            "tool_hooks": lambda: ToolHooksCapability(
                handle.contributions, handle.effects, handle.plugin_id
            ),
            "proactive_gates": lambda: ProactiveGatesCapability(
                handle.contributions, handle.effects
            ),
            "channels": lambda: ChannelsCapability(
                handle.contributions, handle.effects
            ),
            "background": lambda: BackgroundCapability(
                handle.effects, handle.plugin_id
            ),
            "bot_commands": lambda: BotCommandsCapability(
                handle.contributions, handle.effects
            ),
            "rpc": lambda: RpcCapability(
                self.rpc, handle.effects, handle.plugin_id, services.event_bus
            ),
            "dependencies": lambda: PluginDependencies(
                handle.record.manifest.dependencies,
                self._dependency_api,
                optional_declared=handle.record.manifest.optional_dependencies,
            ),
            "runtime": lambda: PluginRuntimeLifecycle(
                services.is_reload,
                handle.drainers,
                was_active=handle.plugin_id in services.previously_active_plugins,
            ),
            "role_runtime_registry": lambda: services.role_runtime_registry,
            # 直传引用，无需 effect 包装：宿主拥有这些服务的生命周期，插件只读，
            # 卸载时无需撤销任何登记。
            "workspace": lambda: services.workspace,
            "role_store": lambda: services.role_store,
            "memory_engine": lambda: services.memory_engine,
            "session_manager": lambda: services.session_manager,
            "light_provider": lambda: services.light_provider,
            "light_model": lambda: services.light_model,
            "relationship_runtime": lambda: services.relationship_runtime,
        }
        return {
            name: builders[name]()
            for name in handle.record.manifest.capabilities
            if name in builders
        }

    async def _rollback_failed_load(
        self, handle: PluginHandle, error: BaseException
    ) -> None:
        logger.warning("插件 %s 加载失败，回滚: %s", handle.record.name, error)
        _ = await handle.effects.dispose_all()
        handle.contributions = type(handle.contributions)()
        handle.instance = None
        handle.drainers.clear()
        handle.state = PluginState.FAILED
        handle.error = error

    # ── 卸载 ──────────────────────────────────────────────────────────────

    def assert_hot_unloadable(self, name: str | None = None) -> None:
        """Preflights the whole strong-dependent closure before any disposal."""
        handles = (
            self._unload_closure(name) if name is not None else self._active_handles()
        )
        unsafe = [
            handle.plugin_id
            for handle in handles
            if not handle.record.manifest.supports_hot_unload
        ]
        if unsafe:
            raise PluginRestartRequired(unsafe)

    def _unload_closure(self, name: str) -> list[PluginHandle]:
        handle = self._handles.get(name)
        if handle is None or handle.state is not PluginState.ACTIVE:
            return []
        closure: list[PluginHandle] = []
        seen: set[str] = set()

        def visit(target: PluginHandle) -> None:
            if target.plugin_id in seen:
                return
            seen.add(target.plugin_id)
            for dependent in reversed(self._active_handles()):
                if target.plugin_id in dependent.record.manifest.dependencies:
                    visit(dependent)
            closure.append(target)

        visit(handle)
        return closure

    async def unload(self, name: str, *, force: bool = False) -> list[Exception]:
        """Disposes a dependency closure; force is reserved for final resource cleanup."""
        closure = self._unload_closure(name)
        if not force:
            self.assert_hot_unloadable(name)
        errors: list[Exception] = []
        for handle in closure:
            errors.extend(await self._dispose_handle(handle))
        return errors

    async def _dispose_handle(self, handle: PluginHandle) -> list[Exception]:
        handle.state = PluginState.UNLOADING
        errors = await handle.effects.dispose_all()
        handle.contributions = type(handle.contributions)()
        handle.instance = None
        handle.drainers.clear()
        handle.state = PluginState.DISPOSED
        if handle.record.name in self._active_order:
            self._active_order.remove(handle.record.name)
        self._handles.pop(handle.record.name, None)
        return errors

    async def terminate_all(self, *, force: bool = False) -> None:
        """Preflights all active plugins, or forcibly releases them on process exit."""
        if not force:
            self.assert_hot_unloadable()
        errors: list[Exception] = []
        for name in list(self._active_order):
            errors.extend(await self.unload(name, force=True))
        # Failed/interrupted loads may own effects without an active-order entry.
        for handle in reversed(list(self._handles.values())):
            errors.extend(await self._dispose_handle(handle))
        if errors:
            raise ExceptionGroup("Plugin cleanup failed", errors)

    def _dependency_api(self, plugin_id: str, optional: bool = False) -> Any:
        for handle in self._active_handles():
            if handle.plugin_id == plugin_id and handle.state is PluginState.ACTIVE:
                if handle.instance is None and not optional:
                    raise PluginDependencyError(f"插件 {plugin_id} 未导出接口")
                return handle.instance
        if optional:
            return None
        raise PluginDependencyError(f"插件 {plugin_id} 不可用")

    async def drain(self) -> None:
        """Waits for plugin-owned work while the retiring transport remains attached."""
        for handle in reversed(self._active_handles()):
            for callback in handle.drainers:
                await callback()

    # ── 聚合面（供宿主接线） ────────────────

    @property
    def loaded_count(self) -> int:
        return len(self._active_order)

    def states(self) -> list[dict[str, Any]]:
        """Returns per-plugin lifecycle snapshots for diagnostics."""
        return [handle.describe() for handle in self._handles.values()]

    def _active_handles(self) -> list[PluginHandle]:
        return [
            self._handles[name] for name in self._active_order if name in self._handles
        ]

    def _collect_phase(self, slot: str) -> list[object]:
        modules: list[object] = []
        for handle in self._active_handles():
            modules.extend(handle.contributions.phase_modules[slot])
        return modules

    @property
    def before_turn_modules(self) -> list[object]:
        return self._collect_phase("before_turn")

    @property
    def before_reasoning_modules(self) -> list[object]:
        return self._collect_phase("before_reasoning")

    @property
    def prompt_render_modules(self) -> list[object]:
        return self._collect_phase("prompt_render")

    @property
    def before_step_modules(self) -> list[object]:
        return self._collect_phase("before_step")

    @property
    def after_step_modules(self) -> list[object]:
        return self._collect_phase("after_step")

    @property
    def after_reasoning_modules(self) -> list[object]:
        return self._collect_phase("after_reasoning")

    @property
    def after_turn_modules(self) -> list[object]:
        return self._collect_phase("after_turn")

    @property
    def tool_hooks(self) -> list[Any]:
        return [
            h
            for handle in self._active_handles()
            for h in handle.contributions.tool_hooks
        ]

    @property
    def channels(self) -> list[Any]:
        return [
            c
            for handle in self._active_handles()
            for c in handle.contributions.channels
        ]

    @property
    def proactive_gates(self) -> list[Any]:
        return [
            g
            for handle in self._active_handles()
            for g in handle.contributions.proactive_gates
        ]

    @property
    def telegram_bot_commands(self) -> list[tuple[str, str]]:
        """Returns active plugins' scoped bot-command contributions."""
        return [
            command
            for handle in self._active_handles()
            for command in handle.contributions.bot_commands
        ]


def _import_module(module_name: str, path: Path) -> None:
    # 把入口文件当成包加载，允许插件内部相对 import；先入 sys.modules 再执行
    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
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
