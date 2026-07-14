from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProactiveConfig:
    """Proactive 配置

    使用预设 + 覆盖的方式配置，大部分算法参数内置在策略中。
    """
    # 必填运行信息
    enabled: bool = False
    default_role_id: str = ""
    default_channel: str = "telegram"
    default_chat_id: str = ""
    model: str = ""
    profile: str = "daily"
    profiles: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)

    # Feed Poller 配置
    feed_poller_interval_seconds: int = 150

    # === 以下参数由预设 + 覆盖控制 ===

    # Trigger 配置
    tick_interval_s0: int = 4800
    tick_interval_s1: int = 2400
    tick_jitter: float = 0.3

    # Gate 配置
    score_llm_threshold: float = 0.40
    judge_send_threshold: float = 0.60

    # Safety 配置
    delivery_dedupe_hours: int = 24
    message_dedupe_recent_n: int = 5

    # === 策略内置参数（不对外暴露，由 presets.STRATEGY_PARAMS 提供） ===

    # 评分权重
    score_weight_energy: float = 0.40
    score_recent_scale: float = 10.0

    # 打断权重
    interrupt_weight_reply: float = 0.35
    interrupt_weight_activity: float = 0.25
    interrupt_weight_fatigue: float = 0.15
    interrupt_activity_decay_minutes: float = 180.0
    interrupt_reply_decay_minutes: float = 120.0
    interrupt_no_reply_decay_minutes: float = 360.0
    interrupt_fatigue_window_hours: int = 24
    interrupt_fatigue_soft_cap: float = 6.0
    interrupt_random_strength: float = 0.12
    interrupt_min_floor: float = 0.08

    # Judge 权重
    judge_weight_urgency: float = 0.15
    judge_weight_balance: float = 0.10
    judge_weight_dynamics: float = 0.10
    judge_weight_information_gap: float = 0.25
    judge_weight_relevance: float = 0.20
    judge_weight_expected_impact: float = 0.20
    judge_urgency_horizon_hours: float = 12.0
    judge_balance_daily_max: int = 8
    judge_veto_balance_min: float = 0.1
    judge_veto_llm_dim_min: int = 2

    # Memory retrieval 细节
    memory_history_gate_enabled: bool = True

    # 去重细节
    message_dedupe_enabled: bool = True

    # 其他
    recent_chat_messages: int = 20
    interval_seconds: int = 1800
    sleep_modifier_sleeping: float = 0.15

    # === v2 Agent Tick（唯一实现） ===
    agent_tick_max_steps: int = 35
    agent_tick_model: str = ""
    agent_tick_content_limit: int = 5
    agent_tick_web_fetch_max_chars: int = 8_000
    drift_enabled: bool = False
    drift_max_steps: int = 20
    drift_min_interval_hours: int = 3
