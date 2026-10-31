"""
配置加载模块
从 config.toml 读取配置，支持 ${ENV_VAR} 格式的环境变量插值。
"""

from __future__ import annotations

from agent.prompting.input_budget import BudgetPolicy

import os
import re
import tomllib
import uuid
from pathlib import Path
from typing import Any, cast

from agent.config_models import (
    Config,
    ModelRegistration,
    WiringConfig,
)
from core.common.workspace import resolve_default_workspace
from proactive_v2.preferences import load_proactive_preferences


def load_config(path: str | Path = "config.toml") -> Config:
    """Loads persisted TOML, migrating legacy tables once first.

    ``load_config_text`` and ``load_config_data`` stay pure: only this path
    rewrites the file, and only when a legacy table is still present.
    """
    config_path = Path(path)
    from bootstrap.memory_config_migration import migrate_legacy_memory_config
    from bootstrap.memory_optimizer_config_migration import (
        migrate_legacy_memory_optimizer_config,
    )
    from bootstrap.proactive_config_migration import migrate_legacy_proactive_config
    from bootstrap.scene_config_migration import migrate_legacy_scene_config

    migrate_legacy_memory_config(config_path)
    migrate_legacy_scene_config(config_path)
    migrate_legacy_memory_optimizer_config(config_path)
    migrate_legacy_proactive_config(config_path)
    return load_config_data(_load_config_data(config_path))


def load_config_data(data: dict[str, Any]) -> Config:
    """Builds a configuration from parsed TOML, including environment resolution."""
    _reject_removed_runtime_config(data)

    llm = _as_dict(data.get("llm"))
    llm_main = _as_dict(llm.get("main"))
    llm_fast = _as_dict(llm.get("fast"))
    llm_agent = _as_dict(llm.get("agent"))
    agent_cfg = _as_dict(data.get("agent"))
    desktop_cfg = _as_dict(data.get("desktop"))
    desktop_chat_cfg = _as_dict(desktop_cfg.get("chat"))
    agent_context = _as_dict(agent_cfg.get("context"))
    agent_tools = _as_dict(agent_cfg.get("tools"))
    wiring = _load_wiring_config(data)
    plugins = _load_plugins_config(data)
    # Validation only, so a bad switch is a config error before any candidate
    # runtime is built. Moves out with the proactive loop (#907 4b).
    load_proactive_preferences(plugins)
    model_registrations = _load_model_registrations(data)
    primary_registration = model_registrations[0] if model_registrations else None

    return Config(
        provider=primary_registration.provider if primary_registration else "",
        model=primary_registration.model if primary_registration else "",
        api_key=primary_registration.api_key if primary_registration else "",
        context_budget=BudgetPolicy(
            **{
                key: agent_context[key]
                for key in ("trigger_ratio", "target_ratio", "safety_margin_tokens")
                if key in agent_context
            }
        ),
        max_tokens=int(agent_cfg.get("max_tokens", data.get("max_tokens", 8192))),
        max_iterations=int(
            agent_cfg.get("max_iterations", data.get("max_iterations", 10))
        ),
        compaction_retained_turns=agent_context.get("compaction_retained_turns", 2),
        summary_token_limit=agent_context.get("summary_token_limit", 2000),
        memory_window=int(
            agent_context.get("memory_window", data.get("memory_window", 40))
        ),
        base_url=primary_registration.base_url if primary_registration else None,
        extra_body=(
            _effort_extra_body(primary_registration.effort)
            if primary_registration
            else {}
        ),
        light_model=str(llm_fast.get("model") or data.get("light_model", "")),
        light_api_key=resolve_config_reference(
            str(llm_fast.get("api_key") or data.get("light_api_key", ""))
        ),
        light_base_url=str(llm_fast.get("base_url") or data.get("light_base_url", "")),
        agent_model=str(llm_agent.get("model") or data.get("agent_model", "")),
        agent_api_key=resolve_config_reference(
            str(llm_agent.get("api_key") or data.get("agent_api_key", ""))
        ),
        agent_base_url=str(llm_agent.get("base_url") or data.get("agent_base_url", "")),
        tool_search_enabled=bool(
            agent_tools.get("search_enabled", data.get("tool_search_enabled", False))
        ),
        spawn_enabled=bool(
            agent_tools.get("spawn_enabled", data.get("spawn_enabled", True))
        ),
        dev_mode=bool(
            agent_cfg.get(
                "dev_mode",
                agent_cfg.get(
                    "dev_model",
                    data.get("dev_mode", data.get("dev_model", False)),
                ),
            )
        ),
        desktop_streaming_enabled=bool(
            desktop_chat_cfg.get("streaming_enabled", False)
        ),
        multimodal=bool(llm_main.get("multimodal", True)),
        wiring=wiring,
        plugins=plugins,
        raw_plugin_configs={
            name: dict(value)
            for name, value in _as_dict(data.get("plugins")).items()
            if isinstance(value, dict)
        },
        model_registrations=model_registrations,
    )


def load_config_text(text: str) -> Config:
    """Validates a configuration candidate without touching the persisted file."""
    return load_config_data(tomllib.loads(text))


def _load_model_registrations(
    data: dict[str, Any],
) -> list[ModelRegistration]:
    llm = data.get("llm", {})
    if not isinstance(llm, dict):
        raise ValueError("llm 必须是对象")
    raw_registrations = llm.get("registrations", [])
    if not isinstance(raw_registrations, list):
        raise ValueError("llm.registrations 必须是数组")
    if any(not isinstance(item, dict) for item in raw_registrations):
        raise ValueError("模型注册必须是对象")
    registrations = [_parse_model_registration(item) for item in raw_registrations]
    _validate_model_registrations(registrations)
    return registrations


def _parse_model_registration(payload: dict[str, Any]) -> ModelRegistration:
    for name in ("id", "provider", "base_url", "api_key", "model", "effort"):
        if name in payload and not isinstance(payload[name], str):
            raise ValueError(f"模型注册 {name} 必须是字符串")
    effort = str(payload.get("effort") or "none").strip().lower()
    if effort not in {"none", "low", "high", "max"}:
        raise ValueError(f"模型注册 Effort 无效: {effort}")
    return ModelRegistration(
        id=str(payload.get("id") or "").strip(),
        provider=str(payload.get("provider") or "openai").strip(),
        base_url=str(payload.get("base_url") or "").strip(),
        api_key=resolve_config_reference(str(payload.get("api_key") or "")),
        model=str(payload.get("model") or "").strip(),
        effort=cast(Any, effort),
        # Legacy context_window_tokens migrates; legacy max_output_tokens is dropped.
        model_context_window=payload.get(
            "model_context_window", payload.get("context_window_tokens")
        ),
        model_auto_compact_token_limit=payload.get("model_auto_compact_token_limit"),
    )


def _validate_model_registrations(registrations: list[ModelRegistration]) -> None:
    ids: set[str] = set()
    for registration in registrations:
        if not registration.id:
            raise ValueError("模型注册必须包含 id")
        try:
            uuid.UUID(registration.id)
        except ValueError as error:
            raise ValueError(f"模型注册 ID 必须是 UUID: {registration.id}") from error
        if registration.id in ids:
            raise ValueError(f"模型注册 ID 重复: {registration.id}")
        ids.add(registration.id)


def _effort_extra_body(effort: str) -> dict[str, Any]:
    return {} if effort == "none" else {"reasoning_effort": effort}


def _load_wiring_config(data: dict) -> WiringConfig:
    agent_cfg = _as_dict(data.get("agent"))
    raw = _as_dict(agent_cfg.get("wiring")) or data.get("wiring", {}) or {}
    toolsets = raw.get(
        "toolsets",
        ["meta_common", "spawn"],
    )
    if not isinstance(toolsets, list) or not toolsets:
        toolsets = ["meta_common", "spawn"]
    return WiringConfig(
        context=str(raw.get("context", "default") or "default"),
        memory=str(raw.get("memory", "default") or "default"),
        toolsets=[str(name) for name in toolsets if str(name).strip()],
    )


def _load_plugins_config(data: dict) -> dict[str, dict[str, Any]]:
    plugins_data = _as_dict(data.get("plugins"))
    plugins: dict[str, dict[str, Any]] = {}
    for name, value in plugins_data.items():
        if isinstance(name, str) and isinstance(value, dict):
            plugins[name] = cast(dict[str, Any], resolve_config_references(value))
    return plugins


def _reject_removed_runtime_config(data: dict) -> None:
    """Rejects configuration for product surfaces removed from the runtime."""
    sections = {
        "channels": {"cli", "qq", "qqbot", "socket", "telegram"},
        "integrations": {"fitbit"},
    }
    for section, names in sections.items():
        values = _as_dict(data.get(section))
        for name in sorted(names):
            if name in values:
                raise ValueError(f"配置项已移除: [{section}.{name}]")
    if "peer_agents" in data:
        raise ValueError("配置项已移除: peer_agents")
    llm = _as_dict(data.get("llm"))
    if "vl" in llm:
        raise ValueError("配置项已移除: [llm.vl]，请改用模型注册和角色视觉模型选择")
    for name in ("vl_model", "vl_api_key", "vl_base_url"):
        if name in data:
            raise ValueError(f"配置项已移除: {name}，请改用模型注册和角色视觉模型选择")


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


_CONFIG_REFERENCE = re.compile(r"\$\{(\w+)\}")


def resolve_config_references(value: object) -> object:
    """Expands every ``${NAME}`` reference in a TOML value, recursing into lists/tables.

    A reference resolves from the process environment, or — when the whole
    string is a bare reference — from ``<workspace>/memory/<NAME>``; one that
    resolves from neither stays verbatim. Callers that persist config must
    write the *unresolved* value back (see ``has_config_reference``), otherwise
    the secret lands in config.toml as plaintext and the reference is lost.
    """
    if isinstance(value, str):
        return resolve_config_reference(value)
    if isinstance(value, list):
        return [resolve_config_references(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): resolve_config_references(item) for key, item in value.items()
        }
    return value


def has_config_reference(value: object) -> bool:
    """Returns whether a TOML value contains a ``${NAME}`` reference anywhere."""
    if isinstance(value, str):
        return _CONFIG_REFERENCE.search(value) is not None
    if isinstance(value, list):
        return any(has_config_reference(item) for item in value)
    if isinstance(value, dict):
        return any(has_config_reference(item) for item in value.values())
    return False


def resolve_config_reference(value: str) -> str:
    """Expands the ``${NAME}`` references in one string (see above).

    Plugins resolve their stored credentials through it (``host.config_references``).
    """
    resolved = _CONFIG_REFERENCE.sub(
        lambda m: os.environ.get(m.group(1), m.group(0)), value
    )
    # 若仍是未展开的占位符，尝试从 workspace/memory/<VAR_NAME> 文件读取
    m = _CONFIG_REFERENCE.fullmatch(resolved)
    if m:
        key_file = resolve_default_workspace() / "memory" / m.group(1)
        if key_file.exists():
            resolved = key_file.read_text(encoding="utf-8").strip()
    return resolved


def _normalize_optional_config_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\$\{(\w+)\}", text):
        return ""
    return text


def _load_config_data(path: str | Path) -> dict:
    path = Path(path)
    if path.suffix.lower() != ".toml":
        raise ValueError(f"主配置仅支持 TOML: {path.suffix}")
    return tomllib.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "Config",
    "has_config_reference",
    "load_config",
    "load_config_data",
    "load_config_text",
    "resolve_config_reference",
    "resolve_config_references",
]
