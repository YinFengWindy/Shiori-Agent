from __future__ import annotations

import shutil
import threading
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from core.common.channel_identifiers import chat_ids_equal
from infra.persistence.json_store import atomic_save_json, load_json

_MANIFEST_VERSION = 2
_DEFAULT_ASSET_CATEGORY_ID = "default"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _normalize_rel_path(path: str | None) -> str | None:
    if not path:
        return None
    return path.replace("\\", "/")


@dataclass(frozen=True)
class RoleChannelBindingConfig:
    """一个角色拥有的渠道会话与其入站白名单。"""

    channel: str
    chat_id: str
    allow_from: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"channel": self.channel, "chat_id": self.chat_id, "allow_from": list(self.allow_from)}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoleChannelBindingConfig":
        channel = str(payload.get("channel") or "").strip()
        chat_id = str(payload.get("chat_id") or "").strip()
        if not channel or not chat_id:
            raise ValueError("角色渠道绑定必须包含 channel 和 chat_id")
        raw_allow_from = payload.get("allow_from", [])
        if not isinstance(raw_allow_from, list):
            raise ValueError("角色渠道 allow_from 必须是数组")
        return cls(
            channel=channel,
            chat_id=chat_id,
            allow_from=sorted({str(item).strip() for item in raw_allow_from if str(item).strip()}),
        )


@dataclass(frozen=True)
class RoleProactiveConfig:
    """角色自己的主动推送目标、策略与 agent 参数。"""

    enabled: bool = False
    target_channel: str = ""
    target_chat_id: str = ""
    profile: str = "daily"
    overrides: dict[str, Any] = field(default_factory=dict)
    agent: dict[str, Any] = field(default_factory=dict)
    drift: dict[str, Any] = field(default_factory=dict)
    policy_configured: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "target_channel": self.target_channel,
            "target_chat_id": self.target_chat_id,
            "profile": self.profile,
            "overrides": dict(self.overrides),
            "agent": dict(self.agent),
            "drift": dict(self.drift),
            "policy_configured": self.policy_configured,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RoleProactiveConfig":
        data = payload if isinstance(payload, dict) else {}
        profile = str(data.get("profile") or "daily").strip()
        if not profile:
            raise ValueError("角色主动推送 profile 不能为空")
        return cls(
            enabled=bool(data.get("enabled", False)),
            target_channel=str(data.get("target_channel") or "").strip(),
            target_chat_id=str(data.get("target_chat_id") or "").strip(),
            profile=profile,
            overrides=_proactive_dict_field(data, "overrides"),
            agent=_proactive_dict_field(data, "agent"),
            drift=_proactive_dict_field(data, "drift"),
            policy_configured=(
                bool(data.get("policy_configured"))
                if "policy_configured" in data
                else any(key in data for key in ("profile", "overrides", "agent", "drift"))
            ),
        )


def _proactive_dict_field(data: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = data.get(field_name, {})
    if not isinstance(value, dict):
        raise ValueError(f"角色主动推送 {field_name} 必须是对象")
    return dict(value)


@dataclass(frozen=True)
class RoleAssetCategory:
    """角色素材库中的单归属分类。"""

    id: str
    name: str
    allow_role_send: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "allow_role_send": self.allow_role_send,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoleAssetCategory":
        category_id = str(payload.get("id") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not category_id or not name:
            raise ValueError("角色素材分类必须包含 id 和 name")
        return cls(
            id=category_id,
            name=name,
            allow_role_send=bool(payload.get("allow_role_send", False)),
        )


def _default_asset_category() -> RoleAssetCategory:
    return RoleAssetCategory(id=_DEFAULT_ASSET_CATEGORY_ID, name="默认")


@dataclass
class RoleRecord:
    """角色聚合根的持久化快照。"""

    id: str
    name: str
    description: str
    system_prompt: str
    background: str
    avatar: str | None
    chat_background: str | None
    illustrations: list[str]
    asset_categories: list[RoleAssetCategory]
    asset_category_bindings: dict[str, str]
    runtime_config: dict[str, Any]
    channel_bindings: list[RoleChannelBindingConfig]
    proactive: RoleProactiveConfig
    memory_init_state: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["avatar"] = _normalize_rel_path(self.avatar)
        payload["chat_background"] = _normalize_rel_path(self.chat_background)
        payload["illustrations"] = [
            _normalize_rel_path(path) or "" for path in self.illustrations
        ]
        payload["asset_categories"] = [
            category.to_dict() for category in self.asset_categories
        ]
        payload["asset_category_bindings"] = {
            _normalize_rel_path(path) or "": category_id
            for path, category_id in self.asset_category_bindings.items()
            if _normalize_rel_path(path)
        }
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoleRecord":
        illustrations = [
            _normalize_rel_path(str(item)) or ""
            for item in payload.get("illustrations", [])
            if str(item).strip()
        ]
        raw_categories = payload.get("asset_categories", [])
        categories = [
            RoleAssetCategory.from_dict(item)
            for item in raw_categories
            if isinstance(item, dict)
        ]
        if not categories:
            categories = [_default_asset_category()]
        category_ids = {category.id for category in categories}
        raw_bindings = payload.get("asset_category_bindings", {})
        binding_items = raw_bindings.items() if isinstance(raw_bindings, dict) else []
        bindings = {
            _normalize_rel_path(str(path)) or "": str(category_id).strip()
            for path, category_id in binding_items
            if str(path).strip()
            and str(category_id).strip() in category_ids
        }
        default_category_id = categories[0].id
        for path in illustrations:
            bindings.setdefault(path, default_category_id)
        return cls(
            id=str(payload.get("id") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            description=str(payload.get("description") or ""),
            system_prompt=str(payload.get("system_prompt") or ""),
            background=str(payload.get("background") or ""),
            avatar=_normalize_rel_path(payload.get("avatar")),
            chat_background=_normalize_rel_path(payload.get("chat_background")),
            illustrations=illustrations,
            asset_categories=categories,
            asset_category_bindings=bindings,
            runtime_config=dict(payload.get("runtime_config") or {}),
            channel_bindings=[
                RoleChannelBindingConfig.from_dict(item)
                for item in payload.get("channel_bindings", [])
                if isinstance(item, dict)
            ],
            proactive=RoleProactiveConfig.from_dict(payload.get("proactive")),
            memory_init_state=dict(payload.get("memory_init_state") or {}),
            created_at=str(payload.get("created_at") or _now_iso()),
            updated_at=str(payload.get("updated_at") or _now_iso()),
        )


class RoleStore:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.roles_dir = workspace / "roles"
        self.assets_dir = self.roles_dir / "assets"
        self.manifest_path = self.roles_dir / "roles.json"
        self._lock = threading.RLock()
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        self.roles_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self._save_roles([])

    def _load_payload(self) -> dict[str, Any]:
        payload = load_json(
            self.manifest_path,
            default={"version": _MANIFEST_VERSION, "roles": []},
            domain="roles",
        )
        if not isinstance(payload, dict):
            raise ValueError("角色清单格式无效：根节点必须是对象")
        roles = payload.get("roles")
        if not isinstance(roles, list):
            raise ValueError("角色清单格式无效：roles 必须是数组")
        migrated = False
        normalized_roles: list[dict[str, Any]] = []
        for item in roles:
            if not isinstance(item, dict):
                raise ValueError("角色清单格式无效：角色记录必须是对象")
            role_payload = dict(item)
            if "featured_image" in role_payload:
                if "chat_background" not in role_payload:
                    role_payload["chat_background"] = role_payload.get("featured_image")
                del role_payload["featured_image"]
                migrated = True
            if not isinstance(role_payload.get("asset_categories"), list):
                role_payload["asset_categories"] = [_default_asset_category().to_dict()]
                migrated = True
            if not isinstance(role_payload.get("asset_category_bindings"), dict):
                raw_categories = role_payload.get("asset_categories")
                first_category_id = (
                    str(raw_categories[0].get("id") or "").strip()
                    if isinstance(raw_categories, list)
                    and raw_categories
                    and isinstance(raw_categories[0], dict)
                    else _DEFAULT_ASSET_CATEGORY_ID
                )
                role_payload["asset_category_bindings"] = {
                    str(path): first_category_id
                    for path in role_payload.get("illustrations", [])
                    if str(path).strip()
                }
                migrated = True
            normalized_roles.append(role_payload)
        if migrated:
            payload = {
                "version": _MANIFEST_VERSION,
                "roles": normalized_roles,
            }
            atomic_save_json(
                self.manifest_path,
                payload,
                domain="roles",
            )
        return {
            "version": max(
                int(payload.get("version") or _MANIFEST_VERSION),
                _MANIFEST_VERSION,
            ),
            "roles": normalized_roles,
        }

    def _save_roles(self, roles: list[RoleRecord]) -> None:
        atomic_save_json(
            self.manifest_path,
            {
                "version": _MANIFEST_VERSION,
                "roles": [role.to_dict() for role in roles],
            },
            domain="roles",
        )

    def _resolve_asset_path(self, rel_path: str | None) -> Path | None:
        normalized = _normalize_rel_path(rel_path)
        if not normalized:
            return None
        target = (self.roles_dir / normalized).resolve()
        assets_root = self.assets_dir.resolve()
        try:
            target.relative_to(assets_root)
        except ValueError:
            raise ValueError(f"角色素材路径越界: {normalized}") from None
        return target

    def _remove_asset_relpath(self, rel_path: str | None) -> None:
        target = self._resolve_asset_path(rel_path)
        if target is None:
            return
        try:
            if target.is_file():
                target.unlink()
        except FileNotFoundError:
            return

    def list_roles(self) -> list[RoleRecord]:
        with self._lock:
            payload = self._load_payload()
            roles = [RoleRecord.from_dict(item) for item in payload["roles"]]
        return sorted(roles, key=lambda item: (item.updated_at, item.id), reverse=True)

    def get_role(self, role_id: str) -> RoleRecord | None:
        role_id = str(role_id).strip()
        if not role_id:
            return None
        for role in self.list_roles():
            if role.id == role_id:
                return role
        return None

    def create_role(
        self,
        *,
        name: str,
        system_prompt: str,
        description: str = "",
        background: str = "",
        runtime_config: dict[str, Any] | None = None,
        role_id: str | None = None,
        avatar_source: str | Path | None = None,
        illustration_sources: list[str | Path] | None = None,
    ) -> RoleRecord:
        clean_name = str(name).strip()
        clean_prompt = str(system_prompt).strip()
        if not clean_name:
            raise ValueError("role.name 不能为空")
        if not clean_prompt:
            raise ValueError("role.system_prompt 不能为空")

        with self._lock:
            roles = self.list_roles()
            resolved_id = (
                str(role_id).strip() if role_id else f"role-{uuid.uuid4().hex[:12]}"
            )
            if any(role.id == resolved_id for role in roles):
                raise ValueError(f"role 已存在: {resolved_id}")
            now = _now_iso()
            record = RoleRecord(
                id=resolved_id,
                name=clean_name,
                description=str(description),
                system_prompt=clean_prompt,
                background=str(background),
                avatar=None,
                chat_background=None,
                illustrations=[],
                asset_categories=[_default_asset_category()],
                asset_category_bindings={},
                runtime_config=dict(runtime_config or {}),
                channel_bindings=[],
                proactive=RoleProactiveConfig(),
                memory_init_state={},
                created_at=now,
                updated_at=now,
            )
            if avatar_source is not None:
                record.avatar = self.import_asset(
                    resolved_id,
                    avatar_source,
                    prefix="avatar",
                )
            if illustration_sources:
                record.illustrations = [
                    self.import_asset(resolved_id, source, prefix="illustration")
                    for source in illustration_sources
                ]
                record.asset_category_bindings = {
                    path: _DEFAULT_ASSET_CATEGORY_ID for path in record.illustrations
                }
            roles.append(record)
            self._save_roles(roles)
            return record

    def update_role(
        self,
        role_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        background: str | None = None,
        runtime_config: dict[str, Any] | None = None,
        channel_bindings: list[RoleChannelBindingConfig | dict[str, Any]] | None = None,
        proactive: RoleProactiveConfig | dict[str, Any] | None = None,
        memory_init_state: dict[str, Any] | None = None,
        avatar_source: str | Path | None = None,
        avatar_asset: str | None = None,
        chat_background: str | None = None,
        clear_chat_background: bool = False,
        clear_avatar: bool = False,
        illustration_sources: list[str | Path] | None = None,
        illustration_category_id: str | None = None,
        removed_illustrations: list[str] | None = None,
        clear_illustrations: bool = False,
        asset_categories: list[RoleAssetCategory | dict[str, Any]] | None = None,
        asset_category_bindings: dict[str, str] | None = None,
    ) -> RoleRecord:
        with self._lock:
            roles = self.list_roles()
            for index, role in enumerate(roles):
                if role.id != role_id:
                    continue
                if name is not None:
                    clean_name = str(name).strip()
                    if not clean_name:
                        raise ValueError("role.name 不能为空")
                    role.name = clean_name
                if description is not None:
                    role.description = str(description)
                if system_prompt is not None:
                    clean_prompt = str(system_prompt).strip()
                    if not clean_prompt:
                        raise ValueError("role.system_prompt 不能为空")
                    role.system_prompt = clean_prompt
                if background is not None:
                    role.background = str(background)
                if runtime_config is not None:
                    role.runtime_config = dict(runtime_config)
                if channel_bindings is not None:
                    role.channel_bindings = self._normalize_channel_bindings(channel_bindings)
                    self._validate_desktop_bindings(role.id, role.channel_bindings)
                    self._ensure_bindings_unique(roles, role.id, role.channel_bindings)
                    if role.proactive.enabled and not any(
                        binding.channel == role.proactive.target_channel
                        and chat_ids_equal(binding.channel, binding.chat_id, role.proactive.target_chat_id)
                        for binding in role.channel_bindings
                    ):
                        role.proactive = replace(
                            role.proactive,
                            enabled=False,
                            target_channel="",
                            target_chat_id="",
                        )
                if proactive is not None:
                    next_proactive = (
                        proactive
                        if isinstance(proactive, RoleProactiveConfig)
                        else RoleProactiveConfig.from_dict(proactive)
                    )
                    if next_proactive.enabled and (
                        not next_proactive.target_channel or not next_proactive.target_chat_id
                    ):
                        raise ValueError("启用主动推送时必须显式选择一个目标渠道")
                    if next_proactive.target_channel and next_proactive.target_chat_id and not any(
                        binding.channel == next_proactive.target_channel
                        and chat_ids_equal(binding.channel, binding.chat_id, next_proactive.target_chat_id)
                        for binding in role.channel_bindings
                    ):
                        raise ValueError("主动推送目标必须是当前角色已绑定的渠道")
                    role.proactive = next_proactive
                if memory_init_state is not None:
                    role.memory_init_state = dict(memory_init_state)
                next_categories = (
                    self._normalize_asset_categories(asset_categories)
                    if asset_categories is not None
                    else role.asset_categories
                )
                next_bindings = (
                    self._normalize_asset_category_bindings(
                        role,
                        asset_category_bindings,
                        categories=next_categories,
                    )
                    if asset_category_bindings is not None
                    else role.asset_category_bindings
                )
                if asset_categories is not None and asset_category_bindings is None:
                    category_ids = {category.id for category in next_categories}
                    invalid_binding = next(
                        (
                            category_id
                            for category_id in role.asset_category_bindings.values()
                            if category_id not in category_ids
                        ),
                        None,
                    )
                    if invalid_binding is not None:
                        raise ValueError(f"素材分类仍被图片使用: {invalid_binding}")
                role.asset_categories = next_categories
                role.asset_category_bindings = next_bindings
                if clear_avatar:
                    self._remove_asset_relpath(role.avatar)
                    role.avatar = None
                if avatar_source is not None:
                    self._remove_asset_relpath(role.avatar)
                    role.avatar = self.import_asset(
                        role.id, avatar_source, prefix="avatar"
                    )
                if avatar_asset is not None:
                    clean_avatar_asset = _normalize_rel_path(avatar_asset)
                    if clean_avatar_asset and not self._is_role_asset_path(
                        role.id, clean_avatar_asset
                    ):
                        raise ValueError(f"角色素材不存在: {clean_avatar_asset}")
                    role.avatar = clean_avatar_asset
                if clear_chat_background:
                    role.chat_background = None
                if chat_background is not None:
                    clean_chat_background = _normalize_rel_path(chat_background)
                    if clean_chat_background and not self._is_role_asset_path(
                        role.id, clean_chat_background
                    ):
                        raise ValueError(f"角色素材不存在: {clean_chat_background}")
                    role.chat_background = clean_chat_background
                if clear_illustrations:
                    for rel_path in role.illustrations:
                        self._remove_asset_relpath(rel_path)
                    role.illustrations = []
                    role.asset_category_bindings = {}
                if removed_illustrations:
                    removed_set = {
                        _normalize_rel_path(str(path)) or ""
                        for path in removed_illustrations
                        if str(path).strip()
                    }
                    if removed_set:
                        kept_illustrations: list[str] = []
                        for rel_path in role.illustrations:
                            normalized = _normalize_rel_path(rel_path) or ""
                            if normalized in removed_set:
                                if role.avatar == normalized:
                                    role.avatar = None
                                if role.chat_background == normalized:
                                    role.chat_background = None
                                self._remove_asset_relpath(normalized)
                                role.asset_category_bindings.pop(normalized, None)
                                continue
                            kept_illustrations.append(rel_path)
                        role.illustrations = kept_illustrations
                if illustration_sources:
                    category_id = str(illustration_category_id or "").strip()
                    if not category_id:
                        category_id = role.asset_categories[0].id
                    if category_id not in {category.id for category in role.asset_categories}:
                        raise ValueError(f"角色素材分类不存在: {category_id}")
                    imported = [
                        self.import_asset(role.id, source, prefix="illustration")
                        for source in illustration_sources
                    ]
                    role.illustrations.extend(imported)
                    role.asset_category_bindings.update(
                        {path: category_id for path in imported}
                    )
                role.updated_at = _now_iso()
                roles[index] = role
                self._save_roles(roles)
                return role
        raise KeyError(f"role 不存在: {role_id}")

    def delete_role(self, role_id: str, *, remove_assets: bool = True) -> bool:
        with self._lock:
            roles = self.list_roles()
            kept = [role for role in roles if role.id != role_id]
            if len(kept) == len(roles):
                return False
            self._save_roles(kept)
            if remove_assets:
                asset_dir = self.assets_dir / role_id
                if asset_dir.exists():
                    shutil.rmtree(asset_dir, ignore_errors=True)
            role_runtime_dir = self.roles_dir / role_id
            if role_runtime_dir.exists():
                shutil.rmtree(role_runtime_dir)
            return True

    def import_asset(
        self,
        role_id: str,
        source: str | Path,
        *,
        prefix: str,
    ) -> str:
        src = Path(source).expanduser()
        if not src.is_file():
            raise FileNotFoundError(f"角色素材不存在: {src}")
        role_assets_dir = self.assets_dir / role_id
        role_assets_dir.mkdir(parents=True, exist_ok=True)
        suffix = src.suffix or ""
        target_name = f"{prefix}-{uuid.uuid4().hex[:8]}{suffix}"
        target = role_assets_dir / target_name
        shutil.copy2(src, target)
        return target.relative_to(self.roles_dir).as_posix()

    def _is_role_asset_path(self, role_id: str, rel_path: str) -> bool:
        normalized = _normalize_rel_path(rel_path)
        if not normalized:
            return False
        target = (self.roles_dir / normalized).resolve()
        role_assets_dir = (self.assets_dir / role_id).resolve()
        try:
            target.relative_to(role_assets_dir)
        except ValueError:
            return False
        return target.is_file()

    def _normalize_channel_bindings(
        self,
        bindings: list[RoleChannelBindingConfig | dict[str, Any]],
    ) -> list[RoleChannelBindingConfig]:
        next_bindings = [
            item if isinstance(item, RoleChannelBindingConfig) else RoleChannelBindingConfig.from_dict(item)
            for item in bindings
        ]
        for index, item in enumerate(next_bindings):
            if any(
                other.channel == item.channel
                and chat_ids_equal(item.channel, other.chat_id, item.chat_id)
                for other in next_bindings[:index]
            ):
                raise ValueError("同一角色不能重复绑定相同渠道会话")
        return next_bindings

    def _normalize_asset_categories(
        self,
        categories: list[RoleAssetCategory | dict[str, Any]],
    ) -> list[RoleAssetCategory]:
        normalized = [
            item if isinstance(item, RoleAssetCategory) else RoleAssetCategory.from_dict(item)
            for item in categories
        ]
        if not normalized:
            raise ValueError("角色素材库至少需要一个分类")
        ids = [category.id for category in normalized]
        names = [category.name.casefold() for category in normalized]
        if len(ids) != len(set(ids)):
            raise ValueError("角色素材分类 id 不能重复")
        if len(names) != len(set(names)):
            raise ValueError("角色素材分类名称不能重复")
        return normalized

    def _normalize_asset_category_bindings(
        self,
        role: RoleRecord,
        bindings: dict[str, str],
        *,
        categories: list[RoleAssetCategory] | None = None,
    ) -> dict[str, str]:
        available_categories = categories or role.asset_categories
        category_ids = {category.id for category in available_categories}
        illustration_paths = set(role.illustrations)
        normalized: dict[str, str] = {}
        for raw_path, raw_category_id in bindings.items():
            path = _normalize_rel_path(str(raw_path)) or ""
            category_id = str(raw_category_id).strip()
            if path not in illustration_paths:
                raise ValueError(f"角色素材不存在: {path}")
            if category_id not in category_ids:
                raise ValueError(f"角色素材分类不存在: {category_id}")
            normalized[path] = category_id
        default_category_id = available_categories[0].id
        for path in role.illustrations:
            normalized.setdefault(path, default_category_id)
        return normalized

    def _ensure_bindings_unique(
        self,
        roles: list[RoleRecord],
        role_id: str,
        bindings: list[RoleChannelBindingConfig],
    ) -> None:
        assigned = {
            (binding.channel, binding.chat_id)
            for other in roles
            if other.id != role_id
            for binding in other.channel_bindings
        }
        conflict = next(
            (
                (binding.channel, binding.chat_id)
                for binding in bindings
                if any(
                    item_channel == binding.channel
                    and chat_ids_equal(binding.channel, item_chat_id, binding.chat_id)
                    for item_channel, item_chat_id in assigned
                )
            ),
            None,
        )
        if conflict is not None:
            raise ValueError(f"渠道会话已绑定其他角色: {conflict[0]}:{conflict[1]}")

    def _validate_desktop_bindings(
        self,
        role_id: str,
        bindings: list[RoleChannelBindingConfig],
    ) -> None:
        expected_chat_id = f"role:{role_id}"
        if any(
            binding.channel == "desktop" and binding.chat_id != expected_chat_id
            for binding in bindings
        ):
            raise ValueError(f"桌面端渠道必须绑定当前角色会话: {expected_chat_id}")
        if any(binding.channel == "desktop" and binding.allow_from for binding in bindings):
            raise ValueError("桌面端渠道不支持允许对象")
