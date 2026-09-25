from __future__ import annotations

import re
from typing import Any

from core.common.channel_chat_types import CHAT_TYPE_GROUP, CHAT_TYPE_PRIVATE, ChatType
from core.common.channel_identifiers import (
    QQ_GROUP_PREFIX,
    bound_qq_group_for_bare_id,
    is_bare_qq_group_chat_id,
    normalize_chat_id,
    normalize_qq_group_chat_id,
)

from .profile_models import RoleProfile

CURRENT_MANIFEST_VERSION = 8

# Telegram addresses groups and channels by negative numeric chat IDs.
_TELEGRAM_GROUP_CHAT_ID = re.compile(r"-\d+")
# QQBot's private chats are declared as ``c2c:<OpenID>``; very old IDs may carry
# a ``qqbot:`` marker, which the transport strips.
_QQBOT_CHANNEL = "qqbot"
_QQBOT_C2C_PREFIX = "c2c:"
_LEGACY_QQBOT_MARKER = "qqbot:"


def migrate_manifest_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Normalize a legacy role manifest into v8 without dropping role-owned data."""

    version = int(payload.get("version") or 0)
    roles = payload.get("roles")
    if not isinstance(roles, list):
        raise ValueError("角色清单格式无效：roles 必须是数组")
    for item in roles:
        if not isinstance(item, dict):
            raise ValueError("角色清单格式无效：角色记录必须是对象")

    legacy_fields = ("pet_packages", "selected_pet_package_id", "desktop_pet_enabled")
    # A stale RoleRecord or older client can submit legacy fields after upgrade.
    # Normalize those writes too; runtime never reads the retired aliases.
    has_legacy_fields = any(
        any(key in role for key in legacy_fields)
        or "auto_scene_cg_enabled" in (role.get("runtime_config") or {})
        for role in roles
    )
    if version == CURRENT_MANIFEST_VERSION and not has_legacy_fields:
        return dict(payload), False
    if version not in {2, 3, 4, 5, 6, 7, CURRENT_MANIFEST_VERSION}:
        raise ValueError(
            f"角色清单版本不支持：需要版本 {CURRENT_MANIFEST_VERSION}，实际为 {version}"
        )

    migrated_roles: list[dict[str, Any]] = []
    for item in roles:
        role = dict(item)
        if not isinstance(role.get("profile"), dict):
            role["profile"] = RoleProfile.from_legacy(
                system_prompt=str(role.get("system_prompt") or ""),
                background=str(role.get("background") or ""),
            ).to_dict()
        if version < 6:
            _prefix_legacy_qq_group_chat_ids(role)
        if version < 7:
            _prefix_legacy_qqbot_chat_ids(role)
            _fill_legacy_chat_types(role)
        if version < 8:
            # Runs after the v6 step, which still reads the old contacts.
            _replace_contacts_with_blocklist(role)
        migrated_roles.append(role)
    # Upgrade-only knowledge: capture fields before RoleRecord drops them, even
    # when the plugin is disabled. One atomic manifest replacement contains both
    # the destination namespace and removal of the legacy source fields.
    plugin_data = dict(payload.get("plugin_data") or {})
    pet_data = dict(plugin_data.get("desktop_pet") or {})
    for role in migrated_roles:
        if any(key in role for key in legacy_fields):
            pet_data.setdefault(
                str(role["id"]), {key: role.get(key) for key in legacy_fields}
            )
            for key in legacy_fields:
                role.pop(key, None)
    novelai_data = dict(plugin_data.get("novelai") or {})
    for role in migrated_roles:
        runtime = dict(role.get("runtime_config") or {})
        if "auto_scene_cg_enabled" in runtime:
            novelai_data.setdefault(
                str(role["id"]),
                {"auto_scene_cg_enabled": runtime.pop("auto_scene_cg_enabled")},
            )
            role["runtime_config"] = runtime
    if novelai_data:
        plugin_data["novelai"] = novelai_data
    if pet_data:
        plugin_data["desktop_pet"] = pet_data
    return {
        **payload,
        "version": CURRENT_MANIFEST_VERSION,
        "roles": migrated_roles,
        "plugin_data": plugin_data,
    }, True


def _prefix_legacy_qq_group_chat_ids(role: dict[str, Any]) -> None:
    """Rewrites pre-v6 bare QQ group IDs to ``gqq:`` in bindings and proactive target.

    The transport sends bare IDs as private messages, so these groups were
    unreachable before the rewrite. Group detection is shared with save-time
    validation through ``is_bare_qq_group_chat_id``.
    """

    raw_bindings = role.get("channel_bindings") or []
    bindings: list[Any] = []
    renamed = False
    for raw in raw_bindings:
        binding = dict(raw) if isinstance(raw, dict) else raw
        # Malformed entries are left for RoleRecord loading to reject.
        if (
            isinstance(binding, dict)
            and binding.get("channel") == "qq"
            and isinstance(binding.get("allow_from", []), list)
            and is_bare_qq_group_chat_id(
                str(binding.get("chat_id") or ""), binding.get("allow_from", [])
            )
        ):
            # normalize_qq_group_chat_id strips before adding the prefix.
            binding["chat_id"] = normalize_qq_group_chat_id(binding["chat_id"])
            renamed = True
        bindings.append(binding)
    if renamed:
        role["channel_bindings"] = bindings
    qq_chat_ids = {
        normalize_chat_id(binding.get("chat_id") or "")
        for binding in bindings
        if isinstance(binding, dict) and binding.get("channel") == "qq"
    }
    proactive = role.get("proactive")
    if not isinstance(proactive, dict) or proactive.get("target_channel") != "qq":
        return
    target = normalize_chat_id(proactive.get("target_chat_id") or "")
    # The old bare==gqq equivalence let a bare target point at a group binding,
    # whether that binding was just renamed or was already stored as ``gqq:``.
    # A bare target that is itself a bound private chat stays private.
    group_chat_id = bound_qq_group_for_bare_id(target, qq_chat_ids)
    if group_chat_id is not None and target not in qq_chat_ids:
        role["proactive"] = {**proactive, "target_chat_id": group_chat_id}


def _prefix_legacy_qqbot_chat_ids(role: dict[str, Any]) -> None:
    """Rewrites pre-v7 ``qqbot`` chat IDs to the declared ``c2c:<OpenID>`` form.

    The QQBot transport reads an ID without a kind (optionally behind the old
    ``qqbot:`` marker) as a C2C chat, so these bindings delivered fine; v7
    validates bindings against the declared ``c2c:`` prefix, and an unprefixed
    one would block every later save of the role. A proactive target naming
    the old ID follows the rewrite. Upgrade-only knowledge of that transport.
    """

    raw_bindings = role.get("channel_bindings")
    if not isinstance(raw_bindings, list):
        return
    renamed: dict[str, str] = {}
    bindings: list[Any] = []
    for raw in raw_bindings:
        # Malformed entries are left for RoleRecord loading to reject.
        if isinstance(raw, dict) and raw.get("channel") == _QQBOT_CHANNEL:
            chat_id = normalize_chat_id(raw.get("chat_id") or "")
            canonical = _canonical_qqbot_chat_id(chat_id)
            if canonical != chat_id:
                renamed[chat_id] = canonical
                raw = {**raw, "chat_id": canonical}
        bindings.append(raw)
    role["channel_bindings"] = bindings
    proactive = role.get("proactive")
    if (
        isinstance(proactive, dict)
        and proactive.get("target_channel") == _QQBOT_CHANNEL
    ):
        target = normalize_chat_id(proactive.get("target_chat_id") or "")
        if target in renamed:
            role["proactive"] = {**proactive, "target_chat_id": renamed[target]}


def _canonical_qqbot_chat_id(chat_id: str) -> str:
    value = chat_id.removeprefix(_LEGACY_QQBOT_MARKER)
    if value and ":" not in value:
        return f"{_QQBOT_C2C_PREFIX}{value}"
    # Another kind (``group:X``) is left untouched: the QQBot transport only
    # sends C2C, so such a binding never delivered, and rewriting it would hide
    # that. Save-time validation against the declared ``c2c:`` type exposes it.
    return value if value.startswith(_QQBOT_C2C_PREFIX) else chat_id


def _fill_legacy_chat_types(role: dict[str, Any]) -> None:
    """Records the session type pre-v7 bindings left implicit in their chat ID.

    Upgrade-only knowledge of the built-in channels' formats: ``qq`` groups are
    ``gqq:`` (already rewritten by the v6 step), ``telegram`` groups are
    negative numbers; everything else, the desktop session included, was a
    private chat. After v7 the type is chosen when binding and never inferred.
    """

    raw_bindings = role.get("channel_bindings")
    if not isinstance(raw_bindings, list):
        return
    bindings: list[Any] = []
    for raw in raw_bindings:
        # Malformed entries are left for RoleRecord loading to reject.
        if isinstance(raw, dict) and "chat_type" not in raw:
            raw = {**raw, "chat_type": _legacy_chat_type(raw)}
        bindings.append(raw)
    role["channel_bindings"] = bindings


def _legacy_chat_type(binding: dict[str, Any]) -> ChatType:
    channel = binding.get("channel")
    chat_id = normalize_chat_id(binding.get("chat_id") or "")
    if channel == "qq" and chat_id.startswith(QQ_GROUP_PREFIX):
        return CHAT_TYPE_GROUP
    if channel == "telegram" and _TELEGRAM_GROUP_CHAT_ID.fullmatch(chat_id):
        return CHAT_TYPE_GROUP
    return CHAT_TYPE_PRIVATE


def _replace_contacts_with_blocklist(role: dict[str, Any]) -> None:
    """Drops pre-v8 single-contact whitelists; group bindings get an empty blacklist.

    Before v8 each external binding admitted only its one ``allow_from``
    contact. A private chat's partner is now the chat itself, and a group
    admits every member not blacklisted, so no old contact carries over: the
    whitelist is not a blacklist, and turning its member into one would block
    the very person it let in.
    """

    raw_bindings = role.get("channel_bindings")
    if not isinstance(raw_bindings, list):
        return
    bindings: list[Any] = []
    for raw in raw_bindings:
        # Malformed entries are left for RoleRecord loading to reject.
        if isinstance(raw, dict):
            raw = {key: value for key, value in raw.items() if key != "allow_from"}
            if raw.get("chat_type") == CHAT_TYPE_GROUP:
                raw["blocked_senders"] = []
        bindings.append(raw)
    role["channel_bindings"] = bindings
