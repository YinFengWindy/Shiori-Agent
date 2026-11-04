"""Construct plugin specs, import verified source and assemble the setup context."""

from __future__ import annotations

import importlib.util
import logging
import sys
from collections.abc import Awaitable, Callable, Collection, Mapping
from importlib.abc import Loader
from pathlib import Path
from typing import Any, cast
from shiori_sdk import PluginRuntimeContext as SdkRuntimeContext
from shiori_sdk.runtime import HostServiceUnavailable
from shiori_sdk.kernel import Context, Kernel, Key, PluginSpec, Scope
from agent.plugin_host.admission import record_execution, runnable, running
from agent.plugin_host.config import PluginConfig
from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.config_schema import (
    PluginConfigSchemaRegistry,
    resolve_config_model,
)
from agent.plugin_host.core_keys import PluginBinding
from agent.plugin_host.dependencies import PluginDependencies, PluginDependencyError
from agent.plugin_host.kv import PluginKVStore, open_plugin_kv
from agent.plugin_host.manifest import ManifestError
from agent.plugin_host.package_fingerprint import PackageContent
from agent.plugin_host.record import PluginRecord
from agent.plugin_host.renderer_communication import RendererCommunication
from agent.plugin_host.renderer_gate import mark_pending
from agent.plugin_host.runtime_context import PluginRuntimeContext
from agent.plugin_host.runtime_lifecycle import PluginRuntimeLifecycle
from agent.plugin_host.settings import PluginGenerationSettings
from agent.plugin_host.state import PluginInstance
from agent.plugin_host.trusted_imports import TrustedPluginImports

# Keep the pre-split logger name so existing filters and diagnostics still match.
logger = logging.getLogger("agent.plugin_host.kernel")


def plugin_key(plugin_id: str) -> Key[Any]:
    """Kernel key under which a plugin provides the API it exposes (``ctx.expose``).

    Manifest ``dependencies`` / ``optional_dependencies`` become kernel
    ``requires`` / ``optional`` on these keys, so the kernel orders setup,
    blocks dependents of an unavailable plugin and builds reload closures.
    """
    return Key(f"plugin:{plugin_id}")


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


def purge_modules(import_path: str) -> None:
    """Remove one activation's package and relative imports from the module cache."""
    for module_name in tuple(sys.modules):
        if module_name == import_path or module_name.startswith(import_path + "."):
            _ = sys.modules.pop(module_name, None)


def import_entry(
    record: PluginRecord, content: PackageContent | None, scope: Scope
) -> None:
    """Import the package using its verified source snapshot when required."""
    if content is None:
        _import_module(record.import_path, record.entry_file)
    else:
        imports = TrustedPluginImports(record.import_path, content.sources)
        imports.install()
        scope.effect(imports.remove, "trusted-source-imports")
        _import_module(
            record.import_path,
            record.entry_file,
            imports.loader(record.import_path, record.entry_file),
        )


def register_config_schema(
    record: PluginRecord, schemas: PluginConfigSchemaRegistry
) -> None:
    """Keep a failed plugin's schema available for repair until actual disposal."""
    if (model_cls := resolve_config_model(record)) is not None:
        schemas.register(record.manifest.id, model_cls)


async def setup_v2(
    record: PluginRecord,
    instance: PluginInstance,
    kernel_context: Context,
    *,
    scope: Scope,
    settings: PluginGenerationSettings,
    namespace: str,
    resolve_reference: Callable[[str], str],
    dependency_api: Callable[[str, bool], Any],
) -> object:
    """Assemble the existing per-plugin context and return its exported API."""
    module = sys.modules[record.import_path]
    setup = getattr(module, "setup", None)
    if not callable(setup):
        raise ManifestError(f"v2 插件 {record.name} 的入口缺少 setup(ctx) 函数")
    setup_fn = cast("Callable[[SdkRuntimeContext], Awaitable[None]]", setup)
    manifest = record.manifest
    plugin_id = manifest.id
    injected = {*manifest.inject, *manifest.optional_inject}
    binding = PluginBinding(
        plugin_id=plugin_id,
        namespace=namespace,
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
            resolve_reference=resolve_reference,
            raw_values=settings.raw_plugin_configs.get(plugin_id),
        ),
        dependencies=PluginDependencies(
            manifest.dependencies,
            dependency_api,
            optional_declared=manifest.optional_dependencies,
        ),
        kv=open_kv(plugin_id, settings.workspace) if "kv" in injected else None,
        runtime=PluginRuntimeLifecycle(
            settings.is_reload or instance.reactivated,
            scope.drainers,
            was_active=instance.reactivated
            or plugin_id in settings.previously_active_plugins,
        ),
        publish_api=publish_api,
        kernel_context=kernel_context,
        binding=binding,
    )
    await setup_fn(context)
    return api


def open_kv(plugin_id: str, workspace: Path | None) -> PluginKVStore:
    """The plugin's KV store under the generation's workspace (``kv``).

    Without a workspace a plugin declaring ``kv`` fails before setup rather
    than falling back to its package directory (#209).
    """
    if workspace is None:
        raise HostServiceUnavailable(
            f"插件 {plugin_id} 注入了 kv，但宿主未提供服务 workspace"
        )
    return open_plugin_kv(workspace=workspace, plugin_id=plugin_id)


def build_spec(
    record: PluginRecord,
    *,
    kernel: Kernel,
    settings: PluginGenerationSettings,
    communication: RendererCommunication,
    namespace: str,
    config_schemas: PluginConfigSchemaRegistry,
    resolve_reference: Callable[[str], str],
    dependency_api: Callable[[str, bool], Any],
    prepared: Callable[[PluginRecord], tuple[PluginInstance, PackageContent | None]],
) -> PluginSpec:
    """Adapt manifest dependencies and admit only a prepared source snapshot."""
    manifest = record.manifest

    async def setup(ctx: Context) -> None:
        instance, content = prepared(record)
        try:
            record_execution(record, content, settings.workspace)
            scope = kernel.scope(manifest.id)
            scope.subscribe(
                lambda: communication.remove_plugin(manifest.id),
                "renderer-communication",
            )
            import_entry(record, content, scope)
            register_config_schema(record, config_schemas)
            api = await setup_v2(
                record,
                instance,
                ctx,
                scope=scope,
                settings=settings,
                namespace=namespace,
                resolve_reference=resolve_reference,
                dependency_api=dependency_api,
            )
            ctx.provide(plugin_key(manifest.id), api)
            mark_pending(instance, record)
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
        replaces=manifest.replaces,
        conflicts=manifest.conflicts,
        runnable=runnable(record, settings),
        hot_reload=manifest.supports_hot_unload,
        channels=bool(record.manifest.channels),
    )


async def activate_plugins(
    activate: Mapping[str, PluginRecord],
    reactivating: frozenset[str],
    kernel: Kernel,
    instances: dict[str, PluginInstance],
) -> None:
    """Create host gates for exactly one activation at a time, in kernel order."""
    for plugin_id in kernel.order():
        if (record := activate.get(plugin_id)) is None:
            continue
        instances[plugin_id] = PluginInstance(
            PluginCallGate(plugin_id), reactivated=plugin_id in reactivating
        )
        try:
            await kernel.activate(plugin_id)
        finally:
            # Interrupted cleanup still owns a scope: retain its gates so
            # force termination can finish the remaining effects.
            if not running(kernel, plugin_id):
                instances.pop(plugin_id, None)
                purge_modules(record.import_path)


def dependency_api(
    plugin_id: str, optional: bool, kernel: Kernel, active_plugin_ids: Collection[str]
) -> Any:
    """Read a declared dependency export only from the current active instance."""
    if plugin_id in active_plugin_ids:
        api = kernel.get(plugin_key(plugin_id))
        if api is None and not optional:
            raise PluginDependencyError(f"插件 {plugin_id} 未导出接口")
        return api
    if optional:
        return None
    raise PluginDependencyError(f"插件 {plugin_id} 不可用")
