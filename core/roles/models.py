from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

DEFAULT_ASSET_CATEGORY_ID = "default"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def normalize_rel_path(path: str | None) -> str | None:
    if not path:
        return None
    return path.replace("\\", "/")


@dataclass(frozen=True)
class RoleChannelBindingConfig:
    """One role-owned channel session and its sole external contact."""

    channel: str
    chat_id: str
    allow_from: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "chat_id": self.chat_id,
            "allow_from": list(self.allow_from),
        }

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
            allow_from=sorted(
                {str(item).strip() for item in raw_allow_from if str(item).strip()}
            ),
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
                else any(
                    key in data for key in ("profile", "overrides", "agent", "drift")
                )
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


def default_asset_category() -> RoleAssetCategory:
    return RoleAssetCategory(id=DEFAULT_ASSET_CATEGORY_ID, name="默认")


@dataclass(frozen=True)
class RolePetPackage:
    """A validated Codex-compatible pet package owned by one role."""

    id: str
    format: str
    display_name: str
    manifest_path: str
    spritesheet_path: str
    imported_at: str
    preview_path: str | None = None
    actions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RolePetPackage":
        package_id = str(payload.get("id") or "").strip()
        display_name = str(payload.get("display_name") or "").strip()
        manifest_path = normalize_rel_path(str(payload.get("manifest_path") or ""))
        spritesheet_path = normalize_rel_path(
            str(payload.get("spritesheet_path") or "")
        )
        if (
            not package_id
            or not display_name
            or not manifest_path
            or not spritesheet_path
        ):
            raise ValueError("桌宠包元数据不完整")
        raw_actions = payload.get("actions", {})
        actions = (
            {
                str(name).strip(): str(state).strip()
                for name, state in raw_actions.items()
                if str(name).strip() and str(state).strip()
            }
            if isinstance(raw_actions, dict)
            else {}
        )
        return cls(
            id=package_id,
            format=str(payload.get("format") or "").strip(),
            display_name=display_name,
            manifest_path=manifest_path,
            spritesheet_path=spritesheet_path,
            imported_at=str(payload.get("imported_at") or now_iso()),
            preview_path=normalize_rel_path(payload.get("preview_path")),
            actions=actions,
        )


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
    pet_packages: list[RolePetPackage] = field(default_factory=list)
    selected_pet_package_id: str | None = None
    desktop_pet_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["avatar"] = normalize_rel_path(self.avatar)
        payload["chat_background"] = normalize_rel_path(self.chat_background)
        payload["illustrations"] = [
            normalize_rel_path(path) or "" for path in self.illustrations
        ]
        payload["asset_categories"] = [
            category.to_dict() for category in self.asset_categories
        ]
        payload["asset_category_bindings"] = {
            normalize_rel_path(path) or "": category_id
            for path, category_id in self.asset_category_bindings.items()
            if normalize_rel_path(path)
        }
        payload["pet_packages"] = [package.to_dict() for package in self.pet_packages]
        payload["selected_pet_package_id"] = self.selected_pet_package_id
        payload["desktop_pet_enabled"] = self.desktop_pet_enabled
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoleRecord":
        illustrations = [
            normalize_rel_path(str(item)) or ""
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
            categories = [default_asset_category()]
        category_ids = {category.id for category in categories}
        raw_bindings = payload.get("asset_category_bindings", {})
        binding_items = raw_bindings.items() if isinstance(raw_bindings, dict) else []
        bindings = {
            normalize_rel_path(str(path)) or "": str(category_id).strip()
            for path, category_id in binding_items
            if str(path).strip() and str(category_id).strip() in category_ids
        }
        default_category_id = categories[0].id
        for path in illustrations:
            bindings.setdefault(path, default_category_id)
        pet_packages = [
            RolePetPackage.from_dict(item)
            for item in payload.get("pet_packages", [])
            if isinstance(item, dict)
        ]
        selected_pet_package_id = (
            str(payload.get("selected_pet_package_id") or "").strip() or None
        )
        if selected_pet_package_id not in {package.id for package in pet_packages}:
            selected_pet_package_id = None
        return cls(
            id=str(payload.get("id") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            description=str(payload.get("description") or ""),
            system_prompt=str(payload.get("system_prompt") or ""),
            background=str(payload.get("background") or ""),
            avatar=normalize_rel_path(payload.get("avatar")),
            chat_background=normalize_rel_path(payload.get("chat_background")),
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
            created_at=str(payload.get("created_at") or now_iso()),
            updated_at=str(payload.get("updated_at") or now_iso()),
            pet_packages=pet_packages,
            selected_pet_package_id=selected_pet_package_id,
            desktop_pet_enabled=bool(payload.get("desktop_pet_enabled", False)),
        )
