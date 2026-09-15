"""插件 manifest：显式声明版本、身份及所需宿主能力。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# manifest 只能声明这里列出的宿主能力
KNOWN_CAPABILITIES = frozenset(
    {
        "tools",
        "lifecycle",
        "tool_hooks",
        "proactive_gates",
        "channels",
        "events",
        "scene_observations",
        "kv",
        "config",
        "background",
        "bot_commands",
        "rpc",
        "dependencies",
        "runtime",
        "role_runtime_registry",
        # 批 B（#183）新增：直传宿主服务引用，供渠道/事件/记忆壳插件读取。这些
        # 字段本身没有装配/回滚语义（不像 tools/kv 等需要 effect 包装），
        # 因此不各建一个 Capability 类，直接在 kernel._build_capabilities 里
        # 透传 HostServices 的同名字段。
        "workspace",
        # 共享宿主那一个 RoleStore 实例。与 workspace 并列而不是让插件自己
        # RoleStore(ctx.workspace)：后者每次都新建一个 RoleManifestRepository，
        # 而写锁是 **按实例的** threading.RLock。两个实例写同一份 roles.json 时
        # atomic_save_json 只保证单次写原子、不防丢更新。
        "role_store",
        "memory_engine",
        "session_manager",
        "light_provider",
        "light_model",
        "relationship_runtime",
    }
)

# 插件包布局为 plugins/<id>/{backend,ui,tests}/，后端入口固定在 backend/ 下
DEFAULT_ENTRY = "backend/plugin.py"


class ManifestError(Exception):
    """manifest 无法读取、解析，或声明不符合插件契约。"""

    metadata: dict[str, object] | None = None


@dataclass
class PluginManifest:
    """插件包声明：身份、入口与所需 capability。"""

    id: str
    # User-facing title; the stable ID still owns lookup, configuration and imports.
    display_name: str | None = None
    version: str | None = None
    desc: str | None = None
    author: str | None = None
    # 插件包统一为 plugins/<id>/{backend,ui,tests}/ 布局（#178），入口默认落在
    # backend/ 下；manifest 显式写 entry 时以它为准。
    entry: str = DEFAULT_ENTRY
    capabilities: tuple[str, ...] = ()
    config_model: str | None = None
    dependencies: tuple[str, ...] = ()
    # Optional APIs never cause provider activation or dependent teardown.
    optional_dependencies: tuple[str, ...] = ()
    api: int = 2
    # False forbids replacing a live instance without restarting the process.
    supports_hot_unload: bool = True
    metadata: dict[str, object] = field(default_factory=dict)


def load_manifest(plugin_dir: Path) -> PluginManifest | None:
    """读取 manifest.yaml；不存在返回 None，格式非法抛 ManifestError。

    只接受显式 ``api: 2``；没有 manifest 的目录不属于插件。
    """
    manifest_path = plugin_dir / "manifest.yaml"
    import yaml

    try:
        if not manifest_path.exists():
            return None
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ManifestError(
            f"manifest.yaml 无法读取或解析: {manifest_path}: {exc}"
        ) from exc
    if not isinstance(loaded, dict):
        raise ManifestError(f"manifest.yaml 格式错误，期望 dict: {manifest_path}")
    raw: dict[str, object] = loaded
    try:
        return _parse_manifest(raw, manifest_path, plugin_dir.name)
    except ManifestError as exc:
        # Preserve opt-in package identity so the host can display a rejection.
        exc.metadata = raw
        raise


def _parse_manifest(
    raw: dict[str, object], manifest_path: Path, directory_name: str
) -> PluginManifest:
    if any(not isinstance(key, str) for key in raw):
        raise ManifestError("manifest keys must be strings")
    if raw.get("api") != 2 or isinstance(raw.get("api"), bool):
        raise ManifestError(f"插件必须显式声明 api: 2: {manifest_path}")
    api = 2
    plugin_id = str(raw.get("id") or raw.get("name") or directory_name)
    supports_hot_unload = raw.get("supports_hot_unload", True)
    if not isinstance(supports_hot_unload, bool):
        raise ManifestError("supports_hot_unload 必须是布尔值")
    capabilities = _parse_capabilities(raw, manifest_path)
    dependencies = _parse_dependencies(raw, "dependencies")
    optional_dependencies = _parse_dependencies(raw, "optional_dependencies")
    if set(dependencies) & set(optional_dependencies):
        raise ManifestError(
            "插件依赖不能同时声明为 dependencies 和 optional_dependencies"
        )
    return PluginManifest(
        id=plugin_id,
        display_name=_optional_str(raw.get("display_name")),
        version=_optional_str(raw.get("version")),
        desc=_optional_str(raw.get("desc")),
        author=_optional_str(raw.get("author")),
        entry=str(raw.get("entry") or DEFAULT_ENTRY),
        capabilities=capabilities,
        config_model=_optional_str(raw.get("config_model")),
        dependencies=dependencies,
        optional_dependencies=optional_dependencies,
        api=api,
        supports_hot_unload=supports_hot_unload,
        metadata={k: v for k, v in raw.items() if isinstance(k, str)},
    )


def _parse_capabilities(raw: dict[str, object], manifest_path: Path) -> tuple[str, ...]:
    value = raw.get("capabilities")
    if value is None:
        raise ManifestError(f"v2 manifest 缺少 capabilities 声明: {manifest_path}")
    if not isinstance(value, list):
        raise ManifestError(f"capabilities 必须是列表: {manifest_path}")
    names = tuple(str(item) for item in value)
    unknown = [name for name in names if name not in KNOWN_CAPABILITIES]
    if unknown:
        raise ManifestError(
            f"manifest 声明了未知 capability {unknown}: {manifest_path}"
        )
    return names


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _parse_dependencies(raw: dict[str, object], field: str) -> tuple[str, ...]:
    value = raw.get(field, [])
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ManifestError(f"{field} 必须是非空插件 ID 的列表")
    return tuple(dict.fromkeys(value))
