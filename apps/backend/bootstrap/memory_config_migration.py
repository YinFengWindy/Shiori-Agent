"""One-shot migration of legacy ``[memory]`` into ``[plugins.default_memory]``.

Work is pending while the file still has a top-level ``memory`` key, or while
``[plugins.default_memory]`` has no explicit ``enabled``. Every migration
deletes ``memory`` and writes an explicit ``enabled``, so a later load finds
nothing to do. The current template writes ``enabled = true`` itself, which
is how a freshly initialized workspace keeps memory on: only workspaces
created from the template count as new installs.

An existing config uses the old loader's actual semantics: a missing
``[memory]`` table or a missing ``memory.enabled`` means disabled. A legacy
``memory.enabled`` overwrites an explicit ``[plugins.default_memory].enabled``.
Embedding credentials are the values the engine would have used, including
fallbacks from ``[llm.fast]``, top-level ``light_*`` and the primary model
registration. The fallback order is decided on resolved values, but the raw
string is written, so a ``${NAME}`` reference stays a reference; the plugin
table is resolved on load. Without a ``[memory]`` table, values already in
the plugin table win over those fallbacks.
A ``memory.engine`` value other than empty or ``default`` is logged and
ignored. That selection is not migrated: enablement and embedding still land
on ``default_memory``, and later engines are inserted only as plugins.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import tomllib
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_PLUGIN_ID = "default_memory"
EMBEDDING_MODEL_KEY = "embedding_model"
EMBEDDING_API_KEY_KEY = "embedding_api_key"
EMBEDDING_BASE_URL_KEY = "embedding_base_url"
OUTPUT_DIMENSIONALITY_KEY = "output_dimensionality"
DEFAULT_EMBEDDING_MODEL = "text-embedding-v3"
# Host-owned enablement key. Matches ``PLUGIN_ENABLED_CONFIG_KEY`` without
# importing the kernel from this module.
_ENABLED_KEY = "enabled"
_LEGACY_DIMENSIONALITY = "memory.embedding.output_dimensionality"
_EDITOR_MODULE = "_shiori_memory_migration_plugin_config_text"
_UNLOCATABLE_MESSAGE = (
    "config.toml 里的 memory 或 plugins.default_memory 写成了内联表或点分键，"
    "无法自动迁移；请先改成独立的 [memory] 与 [plugins.default_memory] 表"
)


def migrate_legacy_memory_config(path: Path) -> None:
    """Migrates ``path`` once; the module docstring says when work is pending."""
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return
    has_legacy_table = "memory" in data
    existing = _existing_plugin_values(data)
    if not has_legacy_table and _ENABLED_KEY in existing:
        return
    migrated = _plugin_values(data)
    if has_legacy_table:
        values = {**existing, **migrated}
        if OUTPUT_DIMENSIONALITY_KEY not in migrated:
            values.pop(OUTPUT_DIMENSIONALITY_KEY, None)
    else:
        values = {**migrated, **existing}
    values[_ENABLED_KEY] = migrated[_ENABLED_KEY]
    updated = _apply(text, values)
    if updated != text:
        _atomic_write(path, updated)


def require_output_dimensionality(value: object, *, field: str) -> int | None:
    """Accepts a missing dimension and rejects non-positive ones."""
    if value in (None, ""):
        return None
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须大于 0") from exc
    if parsed <= 0:
        raise ValueError(f"{field} 必须大于 0")
    return parsed


def _existing_plugin_values(data: dict[str, Any]) -> dict[str, Any]:
    existing = _as_dict(data.get("plugins")).get(DEFAULT_MEMORY_PLUGIN_ID)
    return dict(existing) if isinstance(existing, dict) else {}


def _plugin_values(data: dict[str, Any]) -> dict[str, Any]:
    """Values the old loader would have produced; no ``[memory]`` means disabled."""
    memory = data.get("memory")
    memory = memory if isinstance(memory, dict) else {}
    enabled = bool(memory["enabled"]) if "enabled" in memory else False
    engine = str(memory.get("engine") or "").strip()
    if engine and engine != "default":
        logger.warning(
            "memory.engine=%s 不是 default，已忽略；记忆引擎改由插件开关决定",
            engine,
        )
    embedding = memory.get("embedding")
    embedding = embedding if isinstance(embedding, dict) else {}
    dimensionality = require_output_dimensionality(
        embedding.get("output_dimensionality"),
        field=_LEGACY_DIMENSIONALITY,
    )
    values: dict[str, Any] = {
        _ENABLED_KEY: enabled,
        EMBEDDING_MODEL_KEY: _embedding_model(embedding),
        EMBEDDING_API_KEY_KEY: _embedding_api_key(data, embedding),
        EMBEDDING_BASE_URL_KEY: _embedding_base_url(data, embedding),
    }
    if dimensionality is not None:
        values[OUTPUT_DIMENSIONALITY_KEY] = dimensionality
    return values


def _embedding_model(embedding: dict[str, Any]) -> str:
    if "model" in embedding and embedding["model"] is not None:
        return str(embedding["model"])
    return DEFAULT_EMBEDDING_MODEL


def _embedding_api_key(data: dict[str, Any], embedding: dict[str, Any]) -> str:
    """Returns the raw value of the first source that resolves to a key.

    Resolution only decides the fallback, as the old loader did; the stored
    value stays unresolved so a ``${NAME}`` secret never lands in config.toml
    as plaintext.
    """
    from agent.config import resolve_config_reference

    explicit = str(embedding.get("api_key", ""))
    if resolve_config_reference(explicit):
        return explicit
    llm = _as_dict(data.get("llm"))
    fast = _as_dict(llm.get("fast"))
    light = str(fast.get("api_key") or data.get("light_api_key") or "")
    if resolve_config_reference(light):
        return light
    return str(_primary_registration(llm).get("api_key") or "")


def _embedding_base_url(data: dict[str, Any], embedding: dict[str, Any]) -> str:
    explicit = str(embedding.get("base_url", ""))
    if explicit:
        return explicit
    llm = _as_dict(data.get("llm"))
    fast = _as_dict(llm.get("fast"))
    light = str(fast.get("base_url") or data.get("light_base_url") or "")
    if light:
        return light
    return str(_primary_registration(llm).get("base_url") or "").strip()


def _primary_registration(llm: dict[str, Any]) -> dict[str, Any]:
    registrations = llm.get("registrations")
    if (
        isinstance(registrations, list)
        and registrations
        and isinstance(registrations[0], dict)
    ):
        return registrations[0]
    return {}


def _apply(text: str, values: dict[str, Any]) -> str:
    """Rewrites only the plugin table and drops ``[memory]``, or raises.

    Inline tables and dotted keys have no header line the table editor can
    replace. Rewriting the whole document instead would drop every comment in
    the user's file, so such a config stops startup with a fix-it message.
    """
    editor = _toml_editor()
    try:
        merged = editor.merge_plugin_table(text, DEFAULT_MEMORY_PLUGIN_ID, values)
    except editor.PluginTableConflict as exc:
        raise ValueError(_UNLOCATABLE_MESSAGE) from exc
    updated = editor.remove_table(merged, ["memory"])
    if "memory" in tomllib.loads(updated):
        raise ValueError(_UNLOCATABLE_MESSAGE)
    return updated


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.migrating")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _toml_editor() -> Any:
    cached = sys.modules.get(_EDITOR_MODULE)
    if cached is not None:
        return cached
    path = (
        Path(__file__).resolve().parents[1] / "desktop_bridge" / "plugin_config_text.py"
    )
    spec = importlib.util.spec_from_file_location(_EDITOR_MODULE, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 TOML 表编辑器: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_EDITOR_MODULE] = module
    spec.loader.exec_module(module)
    return module


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
