"""
配置加载模块
从 config.toml 读取配置，支持 ${ENV_VAR} 格式的环境变量插值。
"""

from __future__ import annotations

import logging
import os
import re
import tomllib
import uuid
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from agent.config_models import (
    ChannelsConfig,
    Config,
    MemoryConfig,
    MemoryEmbeddingConfig,
    ModelRegistration,
    QQChannelConfig,
    TelegramChannelConfig,
    WiringConfig,
)
from agent.scene_preferences import load_scene_preferences, migrate_scene_preferences
from agent.voice_config import VoiceAsrConfig, VoiceConfig, VoiceTtsConfig
from core.common.workspace import resolve_default_workspace
from proactive_v2.config import ProactiveConfig
from proactive_v2.config_loader import ProactiveConfigError, load_proactive_config

logger = logging.getLogger(__name__)


def _validated_timezone(tz_name: str, *, enabled: bool) -> str:
    """仅当 anyaction_enabled=True 时校验时区合法性，无效则启动时 fail-fast。"""
    if not enabled:
        return tz_name
    try:
        ZoneInfo(tz_name)
        return tz_name
    except Exception:
        raise ValueError(
            f"proactive.anyaction_timezone 无效: {tz_name!r}，"
            "请使用 IANA 格式，如 'Asia/Shanghai'"
        )


def load_config(path: str | Path = "config.toml") -> Config:
    """Loads and validates the persisted TOML configuration.

    Runs the one-time ``[integrations.novelai]`` -> ``[plugins.novelai]``
    migration (issue #180) against the real file before parsing, so an
    upgrading user's existing token/settings show up under the plugin's own
    config channel with no action required. ``load_config_text`` deliberately
    does not run this: it promises never to touch the persisted file.
    """
    resolved_path = Path(path)
    data = _load_config_data(resolved_path)
    data = _migrate_legacy_novelai_config(resolved_path, data)
    from agent.proactive_preferences import migrate_proactive_preferences

    data = migrate_proactive_preferences(resolved_path, data)
    data = migrate_scene_preferences(resolved_path, data)
    from agent.plugin_preferences import migrate_plugin_preferences

    data = migrate_plugin_preferences(resolved_path, data)
    return load_config_data(data)


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
    agent_maintenance = _as_dict(agent_cfg.get("maintenance"))
    channels = _load_channels_config(data)
    proactive = _load_proactive_config(data)
    from agent.proactive_preferences import load_proactive_preferences

    proactive_strategies = load_proactive_preferences(data)
    memory = _load_memory_config(data)
    voice = _load_voice_config(data)
    wiring = _load_wiring_config(data)
    plugins = _load_plugins_config(data)
    model_registrations = _load_model_registrations(data)
    primary_registration = model_registrations[0] if model_registrations else None

    return Config(
        provider=primary_registration.provider if primary_registration else "",
        model=primary_registration.model if primary_registration else "",
        api_key=primary_registration.api_key if primary_registration else "",
        max_tokens=int(agent_cfg.get("max_tokens", data.get("max_tokens", 8192))),
        max_iterations=int(
            agent_cfg.get("max_iterations", data.get("max_iterations", 10))
        ),
        memory_window=int(
            agent_context.get("memory_window", data.get("memory_window", 40))
        ),
        memory_consolidation_input_token_threshold=max(
            0,
            int(
                agent_maintenance.get(
                    "consolidation_input_token_threshold",
                    75000,
                )
            ),
        ),
        base_url=primary_registration.base_url if primary_registration else None,
        extra_body=(
            _effort_extra_body(primary_registration.effort)
            if primary_registration
            else {}
        ),
        channels=channels,
        proactive=proactive,
        proactive_strategies=proactive_strategies,
        memory_optimizer_enabled=bool(
            agent_maintenance.get(
                "memory_optimizer_enabled",
                data.get("memory_optimizer_enabled", True),
            )
        ),
        memory_optimizer_interval_seconds=int(
            agent_maintenance.get(
                "memory_optimizer_interval_seconds",
                data.get("memory_optimizer_interval_seconds", 64800),
            )
        ),
        light_model=str(llm_fast.get("model") or data.get("light_model", "")),
        light_api_key=_resolve(
            str(llm_fast.get("api_key") or data.get("light_api_key", ""))
        ),
        light_base_url=str(llm_fast.get("base_url") or data.get("light_base_url", "")),
        agent_model=str(llm_agent.get("model") or data.get("agent_model", "")),
        agent_api_key=_resolve(
            str(llm_agent.get("api_key") or data.get("agent_api_key", ""))
        ),
        agent_base_url=str(llm_agent.get("base_url") or data.get("agent_base_url", "")),
        memory=memory,
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
        voice=voice,
        wiring=wiring,
        plugins=plugins,
        scene_observation_enabled=load_scene_preferences(data),
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
        api_key=_resolve(str(payload.get("api_key") or "")),
        model=str(payload.get("model") or "").strip(),
        effort=cast(Any, effort),
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


def _load_channels_config(data: dict) -> ChannelsConfig:
    channels_data = data.get("channels", {})

    telegram = None
    if tg := channels_data.get("telegram"):
        token = _normalize_optional_config_text(_resolve(str(tg.get("token", ""))))
        if bool(tg.get("enabled", True)) and token:
            telegram = TelegramChannelConfig(
                token=token,
                channel_name=str(tg.get("channel_name", "telegram")),
            )

    qq = None
    if qq_data := channels_data.get("qq"):
        bot_uin = _normalize_optional_config_text(str(qq_data.get("bot_uin", "")))
        if bool(qq_data.get("enabled", True)) and bot_uin:
            qq = QQChannelConfig(
                bot_uin=bot_uin,
                websocket_open_timeout_seconds=float(
                    qq_data.get("websocket_open_timeout_seconds", 5.0)
                ),
            )

    return ChannelsConfig(
        telegram=telegram,
        qq=qq,
    )


def _load_proactive_config(data: dict) -> ProactiveConfig:
    proactive = ProactiveConfig()
    if p := data.get("proactive"):
        try:
            proactive = load_proactive_config(p)
        except ProactiveConfigError as e:
            raise ValueError(f"Proactive 配置错误: {e}") from e
    return proactive


def _load_memory_config(data: dict) -> MemoryConfig:
    memory = _as_dict(data.get("memory"))
    embedding = _as_dict(memory.get("embedding"))
    raw_output_dimensionality = embedding.get("output_dimensionality")
    output_dimensionality = (
        int(raw_output_dimensionality)
        if raw_output_dimensionality not in (None, "")
        else None
    )
    if output_dimensionality is not None and output_dimensionality <= 0:
        raise ValueError("memory.embedding.output_dimensionality 必须大于 0")
    return MemoryConfig(
        enabled=bool(memory.get("enabled", False)),
        engine=str(memory.get("engine", "") or ""),
        embedding=MemoryEmbeddingConfig(
            model=str(embedding.get("model", "text-embedding-v3")),
            api_key=_resolve(str(embedding.get("api_key", ""))),
            base_url=str(embedding.get("base_url", "")),
            output_dimensionality=output_dimensionality,
        ),
    )


def _migrate_legacy_novelai_config(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    """One-time, idempotent move of ``[integrations.novelai]`` into ``[plugins.novelai]``.

    Issue #180: novelai's settings moved from the removed ``Config.novelai``
    field to the generic plugin config channel. Older config files still have
    the values under ``[integrations.novelai]``; this rewrites the file once
    so an upgrading user keeps their token/settings with no action required.

    Idempotent by construction, not by a marker: once migrated,
    ``[integrations.novelai]`` is gone from the file, so the guard below finds
    nothing to do on every subsequent load (including a second call in the
    same process). Never overwrites an existing ``[plugins.novelai]`` table
    entry-by-entry — before this ticket the only field that table could ever
    hold is the host-owned ``enabled`` flag (set by the plugin management
    toggle), which is preserved as-is; every other field is not something a
    pre-#180 build could have written there.
    """
    integrations = _as_dict(data.get("integrations"))
    legacy_values = integrations.get("novelai")
    if not isinstance(legacy_values, dict) or not legacy_values:
        return data
    # Local import: keeps this rarely-hit migration path from pulling the
    # desktop bridge's TOML text-splicing module into every config load.
    from desktop_bridge.plugin_config_text import merge_plugin_table, remove_table

    plugins = _as_dict(data.get("plugins"))
    existing = _as_dict(plugins.get("novelai"))
    merged_values: dict[str, Any] = dict(legacy_values)
    if "enabled" in existing:
        merged_values["enabled"] = existing["enabled"]
    text = path.read_text(encoding="utf-8")
    migrated_text = merge_plugin_table(text, "novelai", merged_values)
    migrated_text = remove_table(migrated_text, ["integrations", "novelai"])
    path.write_text(migrated_text, encoding="utf-8")
    logger.info("已将 [integrations.novelai] 一次性迁移至 [plugins.novelai]")
    return tomllib.loads(migrated_text)


def _load_voice_config(data: dict) -> VoiceConfig:
    voice = _as_dict(data.get("voice"))
    asr = _as_dict(voice.get("asr"))
    tts = _as_dict(voice.get("tts"))
    return VoiceConfig(
        enabled=bool(voice.get("enabled", False)),
        hotkey=str(voice.get("hotkey", "Ctrl+Space") or "Ctrl+Space"),
        microphone_device_id=str(voice.get("microphone_device_id", "") or "").strip(),
        asr=VoiceAsrConfig(
            enabled=bool(asr.get("enabled", False)),
            provider=str(asr.get("provider", "tencent") or "tencent"),
            base_url=str(
                asr.get("base_url", "https://asr.tencentcloudapi.com/")
                or "https://asr.tencentcloudapi.com/"
            ),
            secret_id=_resolve(str(asr.get("secret_id", ""))),
            secret_key=_resolve(str(asr.get("secret_key", ""))),
        ),
        tts=VoiceTtsConfig(
            enabled=bool(tts.get("enabled", False)),
            provider=str(tts.get("provider", "minimax") or "minimax"),
            base_url=str(
                tts.get("base_url", "https://api.minimaxi.com/v1/t2a_v2")
                or "https://api.minimaxi.com/v1/t2a_v2"
            ),
            model=str(tts.get("model", "speech-2.8-turbo") or "speech-2.8-turbo"),
            api_key=_resolve(str(tts.get("api_key", ""))),
            volume=float(tts.get("volume", 2.0)),
        ),
    )


def _load_wiring_config(data: dict) -> WiringConfig:
    agent_cfg = _as_dict(data.get("agent"))
    raw = _as_dict(agent_cfg.get("wiring")) or data.get("wiring", {}) or {}
    toolsets = raw.get(
        "toolsets",
        ["meta_common", "spawn", "schedule", "mcp"],
    )
    if not isinstance(toolsets, list) or not toolsets:
        toolsets = ["meta_common", "spawn", "schedule", "mcp"]
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
            plugins[name] = cast(dict[str, Any], _resolve_config_value(value))
    return plugins


def _reject_removed_runtime_config(data: dict) -> None:
    """Rejects configuration for product surfaces removed from the runtime."""
    sections = {
        "channels": {"cli", "qqbot", "socket"},
        "plugins": {"feishu"},
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


def _resolve_config_value(value: object) -> object:
    if isinstance(value, str):
        return _resolve(value)
    if isinstance(value, list):
        return [_resolve_config_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _resolve_config_value(item) for key, item in value.items()}
    return value


def _resolve(value: str) -> str:
    resolved = re.sub(
        r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), value
    )
    # 若仍是未展开的占位符，尝试从 workspace/memory/<VAR_NAME> 文件读取
    m = re.fullmatch(r"\$\{(\w+)\}", resolved)
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
    "ChannelsConfig",
    "Config",
    "MemoryConfig",
    "MemoryEmbeddingConfig",
    "QQChannelConfig",
    "TelegramChannelConfig",
    "_validated_timezone",
    "load_config",
    "load_config_data",
    "load_config_text",
]
