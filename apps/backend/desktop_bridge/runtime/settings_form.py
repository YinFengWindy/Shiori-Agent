"""Form-owned settings drafts preserve tables outside the form's ownership."""

from __future__ import annotations

import tomllib
from typing import Any

from desktop_bridge.runtime.apply import DerivedWrite, RuntimeApplyError
from infra.persistence.toml_store import render_toml

# Match the top-level tables emitted by desktop renderSettingsToml. Everything
# else is opaque to this form, including removed-feature data and plugin values.
_FORM_OWNED_TABLES = frozenset({"llm", "agent", "desktop", "memory"})


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

    def build(current: str) -> str:
        document = tomllib.loads(current)
        preserved = {
            key: value
            for key, value in document.items()
            if key not in _FORM_OWNED_TABLES
        }
        if not preserved:
            return candidate
        # Serialize only the separately owned subtrees, retaining the ordinary
        # settings candidate's intentional deletion/default behavior.
        return candidate.rstrip() + "\n\n" + render_toml(preserved)

    return DerivedWrite(
        build_config_toml=build,
        fingerprint_payload={
            "kind": "settings-form",
            "config_toml": candidate,
            "preserve_plugins": True,
        },
    )
