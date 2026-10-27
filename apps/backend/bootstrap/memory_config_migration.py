"""One-shot migration of legacy ``[memory]`` into ``[plugins.default_memory]``.

The presence of a top-level ``memory`` key is the work marker. After a
successful migration that key is deleted; a later load sees no ``memory``
table and leaves the file alone. A workspace created from the current
template has no ``[memory]`` table, so it is not migrated and the plugin
stays at its manifest default (enabled).

An existing ``[memory]`` table uses the old loader's actual semantics: a
missing ``enabled`` key means disabled. That value overwrites an explicit
``[plugins.default_memory].enabled``. Embedding credentials are the values
the engine would have used, including fallbacks from ``[llm.fast]`` and the
primary model registration, with ``${NAME}`` references materialized.
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


def migrate_legacy_memory_config(path: Path) -> None:
    """Rewrites ``path`` once when it still contains a ``[memory]`` table."""
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return
    if "memory" not in data:
        return
    values = _plugin_values(data)
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


def _plugin_values(data: dict[str, Any]) -> dict[str, Any]:
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
    plugins = data.get("plugins")
    plugins = plugins if isinstance(plugins, dict) else {}
    existing = plugins.get(DEFAULT_MEMORY_PLUGIN_ID)
    values = dict(existing) if isinstance(existing, dict) else {}
    values[EMBEDDING_MODEL_KEY] = _embedding_model(embedding)
    values[EMBEDDING_API_KEY_KEY] = _embedding_api_key(data, embedding)
    values[EMBEDDING_BASE_URL_KEY] = _embedding_base_url(data, embedding)
    if dimensionality is None:
        values.pop(OUTPUT_DIMENSIONALITY_KEY, None)
    else:
        values[OUTPUT_DIMENSIONALITY_KEY] = dimensionality
    values[_ENABLED_KEY] = enabled
    return values


def _embedding_model(embedding: dict[str, Any]) -> str:
    if "model" in embedding and embedding["model"] is not None:
        return str(embedding["model"])
    return DEFAULT_EMBEDDING_MODEL


def _embedding_api_key(data: dict[str, Any], embedding: dict[str, Any]) -> str:
    from agent.config import resolve_config_reference

    explicit = resolve_config_reference(str(embedding.get("api_key", "")))
    if explicit:
        return explicit
    llm = _as_dict(data.get("llm"))
    fast = _as_dict(llm.get("fast"))
    light = resolve_config_reference(
        str(fast.get("api_key") or data.get("light_api_key") or "")
    )
    if light:
        return light
    primary = _primary_registration(llm)
    return resolve_config_reference(str(primary.get("api_key") or ""))


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
    editor = _toml_editor()
    try:
        merged = editor.merge_plugin_table(text, DEFAULT_MEMORY_PLUGIN_ID, values)
    except editor.PluginTableConflict:
        return _dump_without_memory(text, values)
    removed = editor.remove_table(merged, ["memory"])
    if _still_has_memory(removed):
        return _dump_without_memory(text, values)
    return removed


def _still_has_memory(text: str) -> bool:
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return True
    return "memory" in parsed


def _dump_without_memory(text: str, values: dict[str, Any]) -> str:
    import toml

    parsed = tomllib.loads(text)
    parsed.pop("memory", None)
    plugins = parsed.get("plugins")
    plugins = dict(plugins) if isinstance(plugins, dict) else {}
    plugins[DEFAULT_MEMORY_PLUGIN_ID] = values
    parsed["plugins"] = plugins
    return toml.dumps(parsed)


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
