from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from shiori_sdk.values import now_iso, normalize_rel_path

from .profile_models import RoleProfile

DEFAULT_ASSET_CATEGORY_ID = "default"


def normalize_role_id(role_id: str) -> str:
    """Returns a nonempty role identifier for role-owned service paths."""
    clean = str(role_id).strip()
    if not clean:
        raise ValueError("role_id 不能为空")
    return clean


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
    proactive: dict[str, Any]
    memory_init_state: dict[str, Any]
    created_at: str
    updated_at: str
    profile: RoleProfile = field(default_factory=RoleProfile)
    # 按好感阶段名覆盖的语气指引（#714）；没有覆盖的阶段用默认文案。
    affection_stage_prompts: dict[str, str] = field(default_factory=dict)

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
        payload["proactive"] = dict(self.proactive)
        payload["profile"] = self.profile.to_dict()
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
        profile_payload = payload.get("profile")
        profile = (
            RoleProfile.from_dict(profile_payload)
            if isinstance(profile_payload, dict)
            else RoleProfile.from_legacy(
                system_prompt=str(payload.get("system_prompt") or ""),
                background=str(payload.get("background") or ""),
            )
        )
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
            proactive=dict(payload.get("proactive") or {}),
            memory_init_state=dict(payload.get("memory_init_state") or {}),
            created_at=str(payload.get("created_at") or now_iso()),
            updated_at=str(payload.get("updated_at") or now_iso()),
            profile=profile,
            affection_stage_prompts=_stage_prompts_field(
                payload.get("affection_stage_prompts")
            ),
        )


def _stage_prompts_field(value: object) -> dict[str, str]:
    """Keeps the nonblank string overrides; stage names are validated on write."""
    if not isinstance(value, dict):
        return {}
    return {
        str(stage): prompt
        for stage, prompt in value.items()
        if isinstance(prompt, str) and prompt.strip()
    }
