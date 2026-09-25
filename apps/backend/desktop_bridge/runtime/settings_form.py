"""Form-owned settings drafts preserve separately managed plugin values."""

from __future__ import annotations

import tomllib
from typing import Any

from desktop_bridge.runtime.apply import DerivedWrite, RuntimeApplyError
from infra.persistence.toml_store import render_toml

# Top-level tables the settings form does not own: plugin values (edited via
# plugin.config.* / plugins.setEnabled) and host migration receipts. Dropping
# ``_migrations`` on an ordinary save would make a finished one-time upgrade
# (e.g. agent/plugin_default_enabled_migration.py) run again on next start.
_HOST_OWNED_TABLES = ("plugins", "_migrations")


def settings_form_write(payload: dict[str, Any]) -> DerivedWrite | None:
    """Opt-in derived write; raw runtime.apply retains full-document semantics.

    The candidate never carries a plugin snapshot. Its plugin values are read
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
    if "plugins" in parsed:
        raise RuntimeApplyError(
            "runtime_invalid_request", "普通设置草稿不能包含插件配置"
        )
    if "_migrations" in parsed:
        raise RuntimeApplyError(
            "runtime_invalid_request", "普通设置草稿不能包含迁移记录"
        )

    def build(current: str) -> str:
        document = tomllib.loads(current)
        owned = {key: document[key] for key in _HOST_OWNED_TABLES if key in document}
        if not owned:
            return candidate
        # Serialize only the separately owned subtrees, retaining the ordinary
        # settings candidate's intentional deletion/default behavior.
        return candidate.rstrip() + "\n\n" + render_toml(owned)

    return DerivedWrite(
        build_config_toml=build,
        fingerprint_payload={
            "kind": "settings-form",
            "config_toml": candidate,
            "preserve_plugins": True,
        },
    )
