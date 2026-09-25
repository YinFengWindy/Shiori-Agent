"""插件 manifest：显式声明版本、身份及所需宿主能力。"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from core.common.channel_chat_types import (
    CHAT_TYPES,
    ChatTypeDeclaration,
    ChatTypeDeclarations,
)

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


# 渠道名同时是角色绑定、会话线程与消息引用的数据键，限定为可移植的小写标识
_CHANNEL_NAME = re.compile(r"[a-z][a-z0-9_-]{0,63}")
# 宿主自有渠道，插件不能声明
RESERVED_CHANNEL_NAMES = frozenset({"desktop"})
_CHANNEL_REQUIRED_FIELDS = ("name", "label")
_CHANNEL_OPTIONAL_FIELDS = ("contact_label", "chat_id_label", "chat_id_hint")
# 声明了会话类型时，号码的标签与提示由各类型给出，渠道级的这两个字段不再适用
_CHANNEL_CHAT_ID_FIELDS = ("chat_id_label", "chat_id_hint")
_CHAT_TYPE_REQUIRED_FIELDS = ("type", "label", "chat_id_label")
_CHAT_TYPE_OPTIONAL_FIELDS = ("chat_id_hint", "prefix")

# 插件管理页的分组：feature 面向用户的功能，channel 外部渠道，system 宿主内部的
# 护栏与诊断组件（默认折叠）。省略时由 capabilities 推断：声明 channels 即渠道，
# 否则为功能；system 只能显式声明。
PLUGIN_CATEGORIES = ("feature", "channel", "system")


class ManifestError(Exception):
    """manifest 无法读取、解析，或声明不符合插件契约。"""

    metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class ChannelDeclaration:
    """manifest 静态声明的一个外部渠道：插件未激活或未填凭据时也能列出。

    ``name`` 是插件唯一允许经 ``ctx.channels.add`` 贡献的渠道名；其余字段只供
    桌面端绑定面板展示，``contact_label`` 描述 ``allow_from`` 联系人，
    ``chat_id_label`` / ``chat_id_hint`` 描述会话 ID 及其格式。

    ``chat_types`` 声明渠道支持的会话类型（私聊 / 群聊）及其内部前缀：绑定面板
    据此让用户选类型、只填号码，保存绑定时宿主据此校验会话 ID 与类型一致。
    声明了会话类型的渠道不再写渠道级 ``chat_id_label`` / ``chat_id_hint``。
    """

    name: str
    label: str
    contact_label: str | None = None
    chat_id_label: str | None = None
    chat_id_hint: str | None = None
    chat_types: tuple[ChatTypeDeclaration, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Returns the JSON-compatible bridge representation."""
        return {
            "name": self.name,
            "label": self.label,
            "contact_label": self.contact_label,
            "chat_id_label": self.chat_id_label,
            "chat_id_hint": self.chat_id_hint,
            "chat_types": [item.to_dict() for item in self.chat_types],
        }


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
    # Runtime API 2.2：静态渠道声明，需同时声明 channels capability
    channels: tuple[ChannelDeclaration, ...] = ()
    config_model: str | None = None
    dependencies: tuple[str, ...] = ()
    # Optional APIs never cause provider activation or dependent teardown.
    optional_dependencies: tuple[str, ...] = ()
    api: int = 2
    # False forbids replacing a live instance without restarting the process.
    supports_hot_unload: bool = True
    # 插件管理页分组（PLUGIN_CATEGORIES 之一），解析时已按 capabilities 补全默认值
    category: str = "feature"
    # ``[plugins.<id>]`` 没有显式 ``enabled`` 时是否启用；显式值始终优先。
    # 新增 ``false`` 的内置插件要同时登记到 agent/plugin_default_enabled_migration.py，
    # 否则升级用户的插件会被悄悄停用。
    default_enabled: bool = True
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
    default_enabled = raw.get("default_enabled", True)
    if not isinstance(default_enabled, bool):
        raise ManifestError("default_enabled 必须是布尔值")
    capabilities = _parse_capabilities(raw, manifest_path)
    channels = _parse_channels(raw, capabilities)
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
        channels=channels,
        config_model=_optional_str(raw.get("config_model")),
        dependencies=dependencies,
        optional_dependencies=optional_dependencies,
        api=api,
        supports_hot_unload=supports_hot_unload,
        category=_parse_category(raw, capabilities),
        default_enabled=default_enabled,
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


def _parse_channels(
    raw: dict[str, object], capabilities: tuple[str, ...]
) -> tuple[ChannelDeclaration, ...]:
    value = raw.get("channels", [])
    if not isinstance(value, list):
        raise ManifestError("channels 必须是渠道声明列表")
    items: list[object] = value
    if items and "channels" not in capabilities:
        raise ManifestError("声明 channels 的插件必须在 capabilities 中声明 channels")
    declarations: list[ChannelDeclaration] = []
    for index, item in enumerate(items):
        declarations.append(_parse_channel(item, f"channels[{index}]"))
    names = [declaration.name for declaration in declarations]
    if duplicates := sorted({name for name in names if names.count(name) > 1}):
        raise ManifestError(f"channels 重复声明渠道名 {duplicates}")
    return tuple(declarations)


def _parse_channel(item: object, field_name: str) -> ChannelDeclaration:
    if not isinstance(item, dict) or any(not isinstance(key, str) for key in item):
        raise ManifestError(f"{field_name} 必须是对象")
    entry: dict[str, object] = dict(item)
    declares_chat_types = "chat_types" in entry
    raw_chat_types = entry.pop("chat_types", None)
    allowed = {*_CHANNEL_REQUIRED_FIELDS, *_CHANNEL_OPTIONAL_FIELDS}
    values = _parse_string_fields(entry, field_name, allowed, _CHANNEL_REQUIRED_FIELDS)
    name = values["name"]
    if _CHANNEL_NAME.fullmatch(name) is None:
        raise ManifestError(f"{field_name}.name 必须是小写可移植标识: {name!r}")
    if name in RESERVED_CHANNEL_NAMES:
        raise ManifestError(f"{field_name}.name 是宿主保留渠道名: {name}")
    chat_types: tuple[ChatTypeDeclaration, ...] = ()
    if declares_chat_types:
        if conflicting := sorted(set(values) & set(_CHANNEL_CHAT_ID_FIELDS)):
            raise ManifestError(
                f"{field_name} 声明 chat_types 时不能再写 {conflicting}，"
                "号码标签与提示由各会话类型给出"
            )
        chat_types = _parse_chat_types(raw_chat_types, f"{field_name}.chat_types")
    return ChannelDeclaration(
        name=name,
        label=values["label"],
        contact_label=values.get("contact_label"),
        chat_id_label=values.get("chat_id_label"),
        chat_id_hint=values.get("chat_id_hint"),
        chat_types=chat_types,
    )


def _parse_chat_types(
    value: object, field_name: str
) -> tuple[ChatTypeDeclaration, ...]:
    """Parses a channel's session types; types and prefixes must be unambiguous."""
    if not isinstance(value, list) or not value:
        raise ManifestError(f"{field_name} 必须是非空的会话类型列表")
    items: list[object] = value
    declarations: list[ChatTypeDeclaration] = []
    for index, item in enumerate(items):
        item_field = f"{field_name}[{index}]"
        if not isinstance(item, dict) or any(not isinstance(key, str) for key in item):
            raise ManifestError(f"{item_field} 必须是对象")
        values = _parse_string_fields(
            item,
            item_field,
            {*_CHAT_TYPE_REQUIRED_FIELDS, *_CHAT_TYPE_OPTIONAL_FIELDS},
            _CHAT_TYPE_REQUIRED_FIELDS,
        )
        if values["type"] not in CHAT_TYPES:
            raise ManifestError(
                f"{item_field}.type 必须是 {' / '.join(CHAT_TYPES)} 之一"
            )
        prefix = values.get("prefix")
        if prefix is not None and prefix != prefix.strip():
            raise ManifestError(f"{item_field}.prefix 不能含首尾空白")
        declarations.append(ChatTypeDeclaration(**values))
    types = [item.type for item in declarations]
    if duplicates := sorted({name for name in types if types.count(name) > 1}):
        raise ManifestError(f"{field_name} 重复声明会话类型 {duplicates}")
    prefixes = [item.prefix for item in declarations if item.prefix is not None]
    # 一个前缀若是另一个的开头，带长前缀的会话 ID 就无法判定属于哪种类型
    for index, prefix in enumerate(prefixes):
        if any(
            other.startswith(prefix) or prefix.startswith(other)
            for other in prefixes[index + 1 :]
        ):
            raise ManifestError(f"{field_name} 的前缀互相包含，无法区分会话类型")
    return tuple(declarations)


def _parse_string_fields(
    entry: dict[str, object],
    field_name: str,
    allowed: set[str],
    required: tuple[str, ...],
) -> dict[str, str]:
    """Validates a declaration object whose fields are all non-empty strings."""
    if unknown := sorted(set(entry) - allowed):
        raise ManifestError(f"{field_name} 含未知字段 {unknown}")
    values: dict[str, str] = {}
    for key, value in entry.items():
        if not isinstance(value, str) or not value.strip():
            raise ManifestError(f"{field_name}.{key} 必须是非空字符串")
        values[key] = value
    for key in required:
        if key not in values:
            raise ManifestError(f"{field_name} 缺少 {key}")
    return values


def declared_chat_types(manifests: Iterable[PluginManifest]) -> ChatTypeDeclarations:
    """Collects every declared channel's session types for role binding checks.

    Declarations are static, so disabled or failed plugins still contribute.
    A channel name claimed twice only occurs between CONFLICT candidates; the
    first declaration wins, matching ``channels.list``.
    """
    result: dict[str, tuple[ChatTypeDeclaration, ...]] = {}
    for manifest in manifests:
        for declaration in manifest.channels:
            if declaration.chat_types:
                result.setdefault(declaration.name, declaration.chat_types)
    return result


def _parse_category(raw: dict[str, object], capabilities: tuple[str, ...]) -> str:
    value = raw.get("category")
    if value is None:
        return "channel" if "channels" in capabilities else "feature"
    if not isinstance(value, str) or value not in PLUGIN_CATEGORIES:
        raise ManifestError(f"category 必须是 {' / '.join(PLUGIN_CATEGORIES)} 之一")
    return value


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _parse_dependencies(raw: dict[str, object], field: str) -> tuple[str, ...]:
    value = raw.get(field, [])
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ManifestError(f"{field} 必须是非空插件 ID 的列表")
    return tuple(dict.fromkeys(value))
