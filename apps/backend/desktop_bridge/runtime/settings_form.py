"""Form-owned settings drafts preserve tables outside the form's ownership."""

from __future__ import annotations

import tomllib
from typing import Any

from desktop_bridge.runtime.apply import DerivedWrite, RuntimeApplyError
from infra.persistence.toml_store import render_toml

# Match the top-level tables emitted by desktop renderSettingsToml. Everything
# else is opaque to this form, including plugin values and a leftover [memory]
# table. The next config load migrates that table; owning it here would delete
# it on save before the credentials were copied.
_FORM_OWNED_TABLES = frozenset({"llm", "agent", "desktop"})
_MISSING = object()


def settings_form_write(payload: dict[str, Any]) -> DerivedWrite | None:
    """Opt-in derived write; raw runtime.apply retains full-document semantics.

    The candidate never carries an unrelated snapshot. Opaque values are read
    only when RuntimeSettingsApplication executes the callback under its lock.
    The fingerprint uses the user's draft, so retries remain idempotent after
    unrelated plugin changes.
    """
    preserve = payload.get("preserve_plugins", False)
    if not isinstance(preserve, bool):
        raise RuntimeApplyError(
            "runtime_invalid_request", "preserve_plugins 必须是布尔值"
        )
    if not preserve:
        return None
    candidate = payload.get("config_toml")
    if not isinstance(candidate, str):
        raise RuntimeApplyError("runtime_invalid_request", "配置内容不能为空")
    try:
        parsed = tomllib.loads(candidate)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeApplyError(
            "runtime_invalid_request", f"配置内容无法解析: {exc}"
        ) from exc
    unowned = set(parsed) - _FORM_OWNED_TABLES
    if unowned:
        raise RuntimeApplyError(
            "runtime_invalid_request",
            f"普通设置草稿不能修改独立配置: {', '.join(sorted(unowned))}",
        )
    scene_enabled = payload.get("scene_observation_enabled", _MISSING)
    if scene_enabled is not _MISSING and not isinstance(scene_enabled, bool):
        raise RuntimeApplyError(
            "runtime_invalid_request", "scene_observation_enabled 必须是布尔值"
        )
    proactive_strategies = _proactive_strategies(payload)

    def build(current: str) -> str:
        document = tomllib.loads(current)
        preserved = {
            key: value
            for key, value in document.items()
            if key not in _FORM_OWNED_TABLES
        }
        if isinstance(scene_enabled, bool):
            _merge_scene_observation(preserved, scene_enabled)
        if proactive_strategies:
            _merge_proactive_strategies(preserved, proactive_strategies)
        if not preserved:
            return candidate
        # Serialize only the separately owned subtrees, retaining the ordinary
        # settings candidate's intentional deletion/default behavior.
        return candidate.rstrip() + "\n\n" + render_toml(preserved)

    fingerprint: dict[str, Any] = {
        "kind": "settings-form",
        "config_toml": candidate,
        "preserve_plugins": True,
    }
    if isinstance(scene_enabled, bool):
        fingerprint["scene_observation_enabled"] = scene_enabled
    if proactive_strategies is not None:
        fingerprint["proactive_strategies"] = proactive_strategies
    return DerivedWrite(
        build_config_toml=build,
        fingerprint_payload=fingerprint,
    )


def _merge_scene_observation(preserved: dict[str, Any], enabled: bool) -> None:
    """Sets ``observation_enabled`` and keeps every other plugin key."""
    plugins = preserved.get("plugins")
    if plugins is None:
        plugins = {}
        preserved["plugins"] = plugins
    if not isinstance(plugins, dict):
        raise RuntimeApplyError("runtime_invalid_request", "plugins 必须是表")
    scene = plugins.get("scene")
    if scene is None:
        scene = {}
        plugins["scene"] = scene
    if not isinstance(scene, dict):
        raise RuntimeApplyError("runtime_invalid_request", "plugins.scene 必须是表")
    scene["observation_enabled"] = enabled


_STRATEGY_KEYS = ("scene_followup", "relationship")


def _proactive_strategies(payload: dict[str, Any]) -> dict[str, bool] | None:
    """Explicit switches to merge, or ``None`` when the save does not touch them."""
    raw = payload.get("proactive_strategies", _MISSING)
    if raw is _MISSING:
        return None
    if not isinstance(raw, dict) or set(raw) - set(_STRATEGY_KEYS):
        raise RuntimeApplyError(
            "runtime_invalid_request",
            "proactive_strategies 只能有 scene_followup 与 relationship",
        )
    if any(not isinstance(value, bool) for value in raw.values()):
        raise RuntimeApplyError(
            "runtime_invalid_request", "proactive_strategies 的开关必须是布尔值"
        )
    return {key: value for key, value in raw.items() if key in _STRATEGY_KEYS}


def _merge_proactive_strategies(
    preserved: dict[str, Any], strategies: dict[str, bool]
) -> None:
    """Sets the given switches and keeps every other plugin key."""
    plugins = preserved.get("plugins")
    if plugins is None:
        plugins = {}
        preserved["plugins"] = plugins
    if not isinstance(plugins, dict):
        raise RuntimeApplyError("runtime_invalid_request", "plugins 必须是表")
    table = plugins.get("proactive")
    if table is None:
        table = {}
        plugins["proactive"] = table
    if not isinstance(table, dict):
        raise RuntimeApplyError("runtime_invalid_request", "plugins.proactive 必须是表")
    table.update(strategies)
