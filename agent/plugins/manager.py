from __future__ import annotations

import functools
import importlib.util
import inspect
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from agent.lifecycle.types import (
    AfterReasoningCtx,
    AfterStepCtx,
    AfterToolResultCtx,
    AfterTurnCtx,
    BeforeReasoningCtx,
    BeforeStepCtx,
    BeforeToolCallCtx,
    BeforeTurnCtx,
    PreToolCtx,
    PromptRenderCtx,
)
from agent.plugins.registry import MetadataKind, PluginEventType, plugin_registry
from agent.plugins.manifest import (
    PluginManifest,
    PluginManifestError,
    load_plugin_manifest,
    peek_plugin_id,
)
from agent.plugins.resources import PluginResourceScope
from agent.tool_hooks.base import ToolHook
from agent.tool_hooks.types import HookContext, HookOutcome
from agent.core.proactive_turn.gates import ProactiveGate
from bus.event_bus import EventBus
from infra.channels.contract import Channel

logger = logging.getLogger(__name__)
_EVENT_TYPE_MAP: dict[PluginEventType, type] = {
    PluginEventType.BEFORE_TURN: BeforeTurnCtx,
    PluginEventType.BEFORE_REASONING: BeforeReasoningCtx,
    PluginEventType.PROMPT_RENDER: PromptRenderCtx,
    PluginEventType.BEFORE_STEP: BeforeStepCtx,
    PluginEventType.AFTER_STEP: AfterStepCtx,
    PluginEventType.AFTER_REASONING: AfterReasoningCtx,
    PluginEventType.AFTER_TURN: AfterTurnCtx,
    PluginEventType.BEFORE_TOOL_CALL: BeforeToolCallCtx,
    PluginEventType.AFTER_TOOL_RESULT: AfterToolResultCtx,
}


@dataclass
class _LoadedPlugin:
    module_path: str
    manifest: PluginManifest
    instance: object
    resources: PluginResourceScope
    tool_hooks: tuple[ToolHook, ...]
    proactive_gates: tuple[ProactiveGate, ...]
    before_turn_modules: tuple[object, ...]
    before_reasoning_modules: tuple[object, ...]
    prompt_render_modules: tuple[object, ...]
    before_step_modules: tuple[object, ...]
    after_step_modules: tuple[object, ...]
    after_reasoning_modules: tuple[object, ...]
    after_turn_modules: tuple[object, ...]
    channels: tuple[Channel, ...]


class PluginUnavailableError(RuntimeError):
    """Raised when an RPC targets a plugin that is not loaded."""

    def __init__(self, plugin_id: str) -> None:
        self.plugin_id = plugin_id
        super().__init__(f"plugin unavailable: {plugin_id}")


class PluginMethodDeniedError(RuntimeError):
    """Raised when a loaded plugin did not declare an RPC method."""

    def __init__(self, plugin_id: str, method: str) -> None:
        self.plugin_id = plugin_id
        self.method = method
        super().__init__(f"plugin method denied: {method}")


class PluginManager:
    def __init__(
        self,
        plugin_dirs: list[Path],
        *,
        event_bus: EventBus,
        tool_registry: Any = None,
        workspace: Path | None = None,
        session_manager: Any = None,
        memory_engine: Any = None,
        app_config: Any = None,
        light_provider: Any = None,
        light_model: str = "",
        plugin_configs: dict[str, dict[str, Any]] | None = None,
        relationship_runtime: Any = None,
    ) -> None:
        self._dirs = plugin_dirs
        self._event_bus = event_bus
        self._tool_registry = tool_registry
        self._workspace = workspace
        self._session_manager = session_manager
        self._memory_engine = memory_engine
        self._relationship_runtime = relationship_runtime
        self._app_config = app_config
        self._light_provider = light_provider
        self._light_model = light_model
        self._plugin_configs = plugin_configs or {}
        self._loaded: set[str] = set()
        self._loaded_by_id: dict[str, _LoadedPlugin] = {}
        self._known_plugin_ids: set[str] = set()
        self._channels: list[Channel] = []
        self._tool_hooks: list[ToolHook] = []
        self._proactive_gates: list[ProactiveGate] = []
        self._before_turn_modules: list[object] = []
        self._before_reasoning_modules: list[object] = []
        self._prompt_render_modules: list[object] = []
        self._before_step_modules: list[object] = []
        self._after_step_modules: list[object] = []
        self._after_reasoning_modules: list[object] = []
        self._after_turn_modules: list[object] = []

    @property
    def loaded_count(self) -> int:
        return len(self._loaded)

    @property
    def loaded_plugin_ids(self) -> tuple[str, ...]:
        """Returns loaded plugin IDs in stable order."""

        return tuple(sorted(self._loaded_by_id))

    def public_manifests(self) -> list[dict[str, object]]:
        """Returns renderer-safe manifests for successfully loaded plugins."""

        return [
            self._loaded_by_id[plugin_id].manifest.to_public_dict()
            for plugin_id in sorted(self._loaded_by_id)
        ]

    def authorize_rpc(
        self,
        method: str,
        *,
        known_prefixes: set[str] | None = None,
    ) -> None:
        """Rejects unavailable or undeclared plugin RPC methods."""

        plugin_id, separator, _ = method.partition(".")
        if not separator:
            return
        known = self._known_plugin_ids | (known_prefixes or set())
        if plugin_id not in known:
            return
        loaded = self._loaded_by_id.get(plugin_id)
        if loaded is None:
            raise PluginUnavailableError(plugin_id)
        if method not in loaded.manifest.rpc_methods:
            raise PluginMethodDeniedError(plugin_id, method)

    @property
    def tool_hooks(self) -> list[ToolHook]:
        return list(self._tool_hooks)

    @property
    def channels(self) -> list[Channel]:
        return list(self._channels)

    @property
    def proactive_gates(self) -> list[ProactiveGate]:
        return list(self._proactive_gates)

    @property
    def before_turn_modules(self) -> list[object]:
        return list(self._before_turn_modules)

    @property
    def before_reasoning_modules(self) -> list[object]:
        return list(self._before_reasoning_modules)

    @property
    def prompt_render_modules(self) -> list[object]:
        return list(self._prompt_render_modules)

    @property
    def before_step_modules(self) -> list[object]:
        return list(self._before_step_modules)

    @property
    def after_step_modules(self) -> list[object]:
        return list(self._after_step_modules)

    @property
    def after_reasoning_modules(self) -> list[object]:
        return list(self._after_reasoning_modules)

    @property
    def after_turn_modules(self) -> list[object]:
        return list(self._after_turn_modules)

    @property
    def telegram_bot_commands(self) -> list[tuple[str, str]]:
        commands: list[tuple[str, str]] = []
        for module_path in self._loaded:
            instance = plugin_registry.get_instance(module_path)
            if instance is None:
                continue
            getter = getattr(instance, "telegram_bot_commands", None)
            if getter is None:
                continue
            typed_getter = cast(Callable[[], list[tuple[str, str]]], getter)
            for command, description in typed_getter():
                commands.append((str(command), str(description)))
        return commands

    # 扫描所有 plugin_dirs，返回可加载的插件描述列表
    def discover(self) -> list[dict[str, str]]:
        mods: list[dict[str, str]] = []
        seen_names: set[str] = set()
        self._known_plugin_ids.clear()
        for d in self._dirs:
            if not d.is_dir():
                continue
            source = d.name
            for child in sorted(d.iterdir()):
                # 1. 跳过非目录和没有 plugin.py 的目录
                if not child.is_dir():
                    continue
                main = child / "plugin.py"
                if not main.exists():
                    continue
                # 2. 同名插件 first-wins，后续同名打 warning 跳过
                if child.name in seen_names:
                    logger.warning("插件名重复，跳过: %s (%s)", child.name, main)
                    continue
                seen_names.add(child.name)
                self._known_plugin_ids.add(peek_plugin_id(child, child.name))
                # 3. import_path 带上 source 避免不同目录同名插件覆盖 sys.modules
                mods.append(
                    {
                        "name": child.name,
                        "module_path": str(main),
                        "import_path": f"akasic_plugin_{source}_{child.name}",
                    }
                )
        return mods

    async def load_all(self) -> None:
        for mod in self.discover():
            await self._load_one(mod)

    async def _load_one(self, mod: dict[str, str]) -> None:
        mp = mod["import_path"]
        # 1. 幂等：已加载过直接跳过
        if mp in self._loaded:
            return
        # 1b. 本地禁用标记存在时跳过
        if _is_plugin_disabled(Path(mod["module_path"]).parent):
            logger.info("插件已禁用（plugin.disabled）: %s", mod["name"])
            return
        # 2. 用 importlib 从文件路径加载，不依赖 sys.path
        try:
            self._import_plugin(mp, Path(mod["module_path"]))
        except Exception as e:
            logger.warning("插件 %s 导入失败: %s", mod["name"], e)
            return
        # 3. 导入触发 __init_subclass__，从 registry 取注册的类
        cls = plugin_registry._classes.get(mp)
        if cls is None:
            logger.warning("插件 %s 未注册类", mod["name"])
            return
        # 4. 实例化，读 manifest 覆盖元信息，注入 PluginContext
        instance = cls()
        plugin_dir = Path(mod["module_path"]).parent
        try:
            manifest = load_plugin_manifest(
                plugin_dir,
                fallback_id=mod["name"],
                instance=instance,
            )
        except PluginManifestError as exc:
            logger.warning("插件 %s manifest 无效，跳过: %s", mod["name"], exc)
            plugin_registry.remove_plugin(mp)
            return
        plugin_id = manifest.plugin_id
        if plugin_id in self._loaded_by_id:
            logger.warning("插件 ID 重复，跳过: %s", plugin_id)
            plugin_registry.remove_plugin(mp)
            return
        try:
            plugin_config = _load_plugin_config(
                plugin_dir,
                getattr(cls, "ConfigModel", None),
                self._plugin_configs.get(plugin_id),
            )
        except _PluginConfigError as e:
            logger.warning("插件 %s 配置无效，跳过: %s", mod["name"], e)
            return
        from agent.plugins.context import PluginContext, PluginKVStore

        resources = PluginResourceScope(self._event_bus, self._tool_registry)
        state_path = (
            self._workspace / "private_runtime" / "plugins" / plugin_id / "state.json"
            if self._workspace is not None
            else plugin_dir / ".kv.json"
        )
        instance.context = PluginContext(  # type: ignore[attr-defined]
            event_bus=resources.event_bus,
            tool_registry=resources.tool_registry,
            plugin_id=plugin_id,
            plugin_dir=plugin_dir,
            kv_store=PluginKVStore(state_path),
            config=plugin_config,
            app_config=self._app_config,
            light_provider=self._light_provider,
            light_model=self._light_model,
            workspace=self._workspace,
            session_manager=self._session_manager,
            memory_engine=self._memory_engine,
            relationship_runtime=self._relationship_runtime,
            resources=resources,
        )
        plugin_registry.register_instance(mp, instance)
        starts = self._collection_starts()
        self._bind_handlers(instance, mp, resources)
        self._register_tools(instance, mp, resources)
        self._bind_tool_hooks(instance, mp)
        self._collect_proactive_gates(instance)
        self._collect_before_turn_modules(instance)
        self._collect_before_reasoning_modules(instance)
        self._collect_prompt_render_modules(instance)
        self._collect_before_step_modules(instance)
        self._collect_after_step_modules(instance)
        self._collect_after_reasoning_modules(instance)
        self._collect_after_turn_modules(instance)
        # 5. 给插件机会做异步初始化；失败时回滚所有注册
        try:
            if hasattr(instance, "initialize"):
                await instance.initialize()
        except Exception as e:
            logger.warning("插件 %s 初始化失败，回滚: %s", mod["name"], e)
            try:
                if hasattr(instance, "terminate"):
                    await instance.terminate()
            except Exception as terminate_error:
                logger.warning(
                    "插件初始化回滚 terminate 失败 (%s): %s",
                    plugin_id,
                    terminate_error,
                )
            await resources.release()
            self._rollback_collections(starts)
            plugin_registry.remove_plugin(mp)
            return
        self._loaded.add(mp)
        self._collect_channels(instance)
        self._loaded_by_id[plugin_id] = self._build_loaded_plugin(
            module_path=mp,
            manifest=manifest,
            instance=instance,
            resources=resources,
            starts=starts,
        )
        logger.info("插件已加载: %s", mod["name"])

    def _import_plugin(self, module_name: str, path: Path) -> None:
        # 1. 把 plugin.py 当成包入口加载，允许数字前缀目录里的插件使用相对 import。
        spec = importlib.util.spec_from_file_location(
            module_name,
            path,
            submodule_search_locations=[str(path.parent)],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载插件文件: {path}")
        # 2. 先注册到 sys.modules 再执行，避免插件内部相对 import 找不到自身
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]

    def _register_tools(
        self,
        instance: Any,
        module_path: str,
        resources: PluginResourceScope,
    ) -> list[str]:
        tool_names: list[str] = []
        if self._tool_registry is None:
            return tool_names
        from agent.tools.base import Tool as AgentTool

        for md in plugin_registry.get_handlers_by_module_path(module_path):
            # 1. 只处理 TOOL 类型元数据
            if md.kind != MetadataKind.TOOL:
                continue
            bound = functools.partial(md.handler, instance, None)
            tool_name = md.tool_name or md.handler_name
            description = (md.handler.__doc__ or "").strip()
            schema = md.tool_schema or {
                "type": "object",
                "properties": {},
                "required": [],
            }
            # 2. 动态创建 Tool 子类并绑定 execute
            ToolCls = type(
                f"PluginTool_{tool_name}",
                (AgentTool,),
                {
                    "name": tool_name,
                    "description": description,
                    "parameters": schema,
                    "execute": _make_execute(bound),
                },
            )
            # 3. 注册到 ToolRegistry，标记来源为 plugin
            plugin_name = getattr(instance, "name", None) or module_path
            assert resources.tool_registry is not None
            resources.tool_registry.register(
                ToolCls(),
                risk=md.tool_risk or "read-write",
                always_on=bool(md.tool_always_on),
                search_hint=md.tool_search_hint,
                source_type="plugin",
                source_name=plugin_name,
            )
            tool_names.append(tool_name)
            logger.info("插件工具已注册: %s (来自 %s)", tool_name, plugin_name)
        return tool_names

    def _bind_handlers(
        self,
        instance: Any,
        module_path: str,
        resources: PluginResourceScope,
    ) -> None:
        for md in plugin_registry.get_handlers_by_module_path(module_path):
            # 1. Phase 1 只绑定生命周期 handler，TOOL 类型留给后续 phase
            if md.kind != MetadataKind.LIFECYCLE:
                continue
            # 2. 跳过当前 phase 尚未支持的事件类型
            ctx_type = _EVENT_TYPE_MAP.get(md.event_type)  # type: ignore[arg-type]
            if ctx_type is None:
                continue
            # 3. 绑定 instance 为第一个参数，EventBus 已处理 sync/async，直接注册
            bound = functools.partial(md.handler, instance)
            resources.event_bus.on(ctx_type, bound)

    def _bind_tool_hooks(self, instance: Any, module_path: str) -> None:
        for md in plugin_registry.get_handlers_by_module_path(module_path):
            if md.kind != MetadataKind.TOOL_HOOK:
                continue
            bound = functools.partial(md.handler, instance)
            hook = _PluginToolHook(
                name=f"plugin:{getattr(instance, 'name', module_path)}:{md.handler_name}",
                handler=bound,
                tool_name_filter=md.hook_tool_name,
            )
            self._tool_hooks.append(hook)
            logger.info("插件 tool hook 已注册: %s", hook.name)

    def _collect_before_turn_modules(self, instance: Any) -> None:
        self._collect_phase_modules(
            instance,
            "before_turn_modules",
            self._before_turn_modules,
        )

    def _collect_proactive_gates(self, instance: Any) -> None:
        for gate in _load_module_list(instance, "proactive_gates"):
            if not isinstance(gate, ProactiveGate):
                raise TypeError(
                    f"插件 {type(instance).__name__}.proactive_gates 返回了无效 gate: {type(gate).__name__}"
                )
            self._proactive_gates.append(gate)

    def _collect_before_reasoning_modules(self, instance: Any) -> None:
        self._collect_phase_modules(
            instance,
            "before_reasoning_modules",
            self._before_reasoning_modules,
        )

    def _collect_prompt_render_modules(self, instance: Any) -> None:
        self._collect_phase_modules(
            instance,
            "prompt_render_modules",
            self._prompt_render_modules,
        )

    def _collect_before_step_modules(self, instance: Any) -> None:
        self._collect_phase_modules(
            instance,
            "before_step_modules",
            self._before_step_modules,
        )

    def _collect_after_step_modules(self, instance: Any) -> None:
        self._collect_phase_modules(
            instance,
            "after_step_modules",
            self._after_step_modules,
        )

    def _collect_after_reasoning_modules(self, instance: Any) -> None:
        self._collect_phase_modules(
            instance,
            "after_reasoning_modules",
            self._after_reasoning_modules,
        )

    def _collect_after_turn_modules(self, instance: Any) -> None:
        self._collect_phase_modules(
            instance,
            "after_turn_modules",
            self._after_turn_modules,
        )

    def _collect_channels(self, instance: Any) -> None:
        for channel in _load_module_list(instance, "channels"):
            self._channels.append(cast(Channel, channel))

    def _collect_phase_modules(
        self,
        instance: Any,
        attr_name: str,
        target: list[object],
    ) -> None:
        target.extend(_load_module_list(instance, attr_name))

    def _collection_starts(self) -> dict[str, int]:
        return {
            "tool_hooks": len(self._tool_hooks),
            "proactive_gates": len(self._proactive_gates),
            "before_turn_modules": len(self._before_turn_modules),
            "before_reasoning_modules": len(self._before_reasoning_modules),
            "prompt_render_modules": len(self._prompt_render_modules),
            "before_step_modules": len(self._before_step_modules),
            "after_step_modules": len(self._after_step_modules),
            "after_reasoning_modules": len(self._after_reasoning_modules),
            "after_turn_modules": len(self._after_turn_modules),
            "channels": len(self._channels),
        }

    def _rollback_collections(self, starts: dict[str, int]) -> None:
        del self._tool_hooks[starts["tool_hooks"] :]
        del self._proactive_gates[starts["proactive_gates"] :]
        del self._before_turn_modules[starts["before_turn_modules"] :]
        del self._before_reasoning_modules[starts["before_reasoning_modules"] :]
        del self._prompt_render_modules[starts["prompt_render_modules"] :]
        del self._before_step_modules[starts["before_step_modules"] :]
        del self._after_step_modules[starts["after_step_modules"] :]
        del self._after_reasoning_modules[starts["after_reasoning_modules"] :]
        del self._after_turn_modules[starts["after_turn_modules"] :]
        del self._channels[starts["channels"] :]

    def _build_loaded_plugin(
        self,
        *,
        module_path: str,
        manifest: PluginManifest,
        instance: object,
        resources: PluginResourceScope,
        starts: dict[str, int],
    ) -> _LoadedPlugin:
        return _LoadedPlugin(
            module_path=module_path,
            manifest=manifest,
            instance=instance,
            resources=resources,
            tool_hooks=tuple(self._tool_hooks[starts["tool_hooks"] :]),
            proactive_gates=tuple(self._proactive_gates[starts["proactive_gates"] :]),
            before_turn_modules=tuple(
                self._before_turn_modules[starts["before_turn_modules"] :]
            ),
            before_reasoning_modules=tuple(
                self._before_reasoning_modules[starts["before_reasoning_modules"] :]
            ),
            prompt_render_modules=tuple(
                self._prompt_render_modules[starts["prompt_render_modules"] :]
            ),
            before_step_modules=tuple(
                self._before_step_modules[starts["before_step_modules"] :]
            ),
            after_step_modules=tuple(
                self._after_step_modules[starts["after_step_modules"] :]
            ),
            after_reasoning_modules=tuple(
                self._after_reasoning_modules[starts["after_reasoning_modules"] :]
            ),
            after_turn_modules=tuple(
                self._after_turn_modules[starts["after_turn_modules"] :]
            ),
            channels=tuple(self._channels[starts["channels"] :]),
        )

    async def unload(self, plugin_id: str) -> bool:
        """Unloads one plugin and releases every manager-owned registration."""

        loaded = self._loaded_by_id.pop(plugin_id, None)
        if loaded is None:
            return False
        try:
            if hasattr(loaded.instance, "terminate"):
                await loaded.instance.terminate()  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("插件 terminate 失败 (%s): %s", plugin_id, exc)
        await loaded.resources.release()
        _remove_owned(self._tool_hooks, loaded.tool_hooks)
        _remove_owned(self._proactive_gates, loaded.proactive_gates)
        _remove_owned(self._before_turn_modules, loaded.before_turn_modules)
        _remove_owned(self._before_reasoning_modules, loaded.before_reasoning_modules)
        _remove_owned(self._prompt_render_modules, loaded.prompt_render_modules)
        _remove_owned(self._before_step_modules, loaded.before_step_modules)
        _remove_owned(self._after_step_modules, loaded.after_step_modules)
        _remove_owned(self._after_reasoning_modules, loaded.after_reasoning_modules)
        _remove_owned(self._after_turn_modules, loaded.after_turn_modules)
        _remove_owned(self._channels, loaded.channels)
        self._loaded.discard(loaded.module_path)
        plugin_registry.remove_plugin(loaded.module_path)
        return True

    async def terminate_all(self) -> None:
        for plugin_id in tuple(self.loaded_plugin_ids):
            await self.unload(plugin_id)


class _PluginConfigError(Exception):
    pass


def _load_plugin_config(
    plugin_dir: Path,
    config_model: type[BaseModel] | None = None,
    raw_config: dict[str, Any] | None = None,
) -> Any:
    if config_model is not None:
        try:
            return config_model.model_validate(raw_config or {})
        except ValidationError as e:
            raise _PluginConfigError(_format_validation_error(e)) from e
    # 1. 读取 _conf_schema.json，提取每个字段的 default 值
    from agent.plugins.config import PluginConfig

    schema_path = plugin_dir / "_conf_schema.json"
    if not schema_path.exists():
        return None
    try:
        loaded = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("_conf_schema.json 读取失败 (%s): %s", plugin_dir, e)
        return None
    if not isinstance(loaded, dict):
        logger.warning("_conf_schema.json 格式错误，期望 dict (%s)", plugin_dir)
        return None
    raw: dict[str, object] = cast("dict[str, object]", loaded)
    values: dict[str, Any] = {}
    for key, spec in raw.items():
        if not isinstance(key, str):
            continue
        if not isinstance(spec, dict):
            continue
        if "default" in spec:
            values[key] = spec["default"]
    # 2. 读取 plugin_config.json，用户级覆盖默认值
    override_path = plugin_dir / "plugin_config.json"
    if override_path.exists():
        try:
            override = json.loads(override_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("plugin_config.json 读取失败 (%s): %s", plugin_dir, e)
        else:
            if isinstance(override, dict):
                raw_override: dict[str, object] = cast("dict[str, object]", override)
                for key, value in raw_override.items():
                    if not isinstance(key, str):
                        continue
                    values[key] = value
            else:
                logger.warning(
                    "plugin_config.json 格式错误，期望 dict (%s)", plugin_dir
                )
    return PluginConfig(values)


def _format_validation_error(error: ValidationError) -> str:
    parts: list[str] = []
    for item in error.errors():
        path = ".".join(str(part) for part in item.get("loc", ())) or "<root>"
        parts.append(f"{path}: {item.get('msg', 'invalid')}")
    return "; ".join(parts)


def _load_module_list(instance: Any, method_name: str) -> list[object]:
    provider = getattr(instance, method_name, None)
    if provider is None:
        return []
    if not callable(provider):
        logger.warning(
            "插件 %s.%s 不是可调用对象", type(instance).__name__, method_name
        )
        return []
    try:
        loaded = provider()
    except Exception as e:
        logger.warning(
            "插件 %s.%s 加载失败: %s", type(instance).__name__, method_name, e
        )
        return []
    if loaded is None:
        return []
    if not isinstance(loaded, list):
        logger.warning(
            "插件 %s.%s 返回值不是 list", type(instance).__name__, method_name
        )
        return []
    return loaded


def _remove_owned(target: list[Any], owned: tuple[Any, ...]) -> None:
    owned_ids = {id(item) for item in owned}
    target[:] = [item for item in target if id(item) not in owned_ids]


def _make_execute(bound: Any) -> Any:
    # 预先提取插件函数接受的参数名（排除 self/event），用于过滤 Registry 注入的 context 字段
    sig = inspect.signature(bound)
    accepted = frozenset(
        name for name in sig.parameters if name not in ("self", "event")
    )

    # 工厂函数把 bound 和 accepted 锁进闭包，避免动态 type() 时 self 顶掉 bound
    async def execute(self: Any, **kwargs: Any) -> str:
        filtered = {k: v for k, v in kwargs.items() if k in accepted}
        result = bound(**filtered)
        if inspect.isawaitable(result):
            result = await result
        return str(result)

    return execute


class _PluginToolHook(ToolHook):
    """将插件的 @on_tool_pre handler 适配为 ToolExecutor 的 ToolHook 接口。"""

    event = "pre_tool_use"

    def __init__(
        self,
        name: str,
        handler: Any,
        tool_name_filter: str | None = None,
    ) -> None:
        self.name = name
        self._handler = handler
        self._tool_name_filter = tool_name_filter

    def matches(self, ctx: HookContext) -> bool:
        if self._tool_name_filter is None:
            return True
        return ctx.request.tool_name == self._tool_name_filter

    async def run(self, ctx: HookContext) -> HookOutcome:
        # 1. 构造 PreToolCtx（复制 arguments，避免插件直接改原对象）
        event = PreToolCtx(
            session_key=ctx.request.session_key,
            channel=ctx.request.channel,
            chat_id=ctx.request.chat_id,
            tool_name=ctx.request.tool_name,
            arguments=dict(ctx.current_arguments),
            call_id=ctx.request.call_id,
            source=ctx.request.source,
            request_text=ctx.request.request_text,
            tool_batch=ctx.request.tool_batch,
            tool_batch_index=ctx.request.tool_batch_index,
        )
        # 2. 调插件 handler，返回值决定行为
        result = self._handler(event)
        if inspect.isawaitable(result):
            result = await result
        # 3. None → 不改参；dict → 新 arguments；HookOutcome → 允许插件直接 deny
        if result is None:
            return HookOutcome()
        if isinstance(result, HookOutcome):
            return result
        if isinstance(result, dict):
            return HookOutcome(updated_input=cast("dict[str, Any]", result))
        return HookOutcome()


def _is_plugin_disabled(plugin_dir: Path) -> bool:
    return (plugin_dir / "plugin.disabled").exists()
