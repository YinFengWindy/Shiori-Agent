"""Proactive 预设配置定义"""

from __future__ import annotations

from typing import TypedDict


class TriggerPreset(TypedDict):
    tick_interval_s0: int
    tick_interval_s1: int
    tick_jitter: float


class GatePreset(TypedDict):
    score_llm_threshold: float
    judge_send_threshold: float
    judge_balance_daily_max: int


class SafetyPreset(TypedDict):
    delivery_dedupe_hours: int
    message_dedupe_recent_n: int


class PresetConfig(TypedDict):
    trigger: TriggerPreset
    gate: GatePreset
    safety: SafetyPreset


# 预设定义
PRESETS: dict[str, PresetConfig] = {
    "daily": {
        # 基于你当前实际使用的配置
        "trigger": {
            "tick_interval_s0": 480,  # 8分钟
            "tick_interval_s1": 240,  # 4分钟
            "tick_jitter": 0.2,
        },
        "gate": {
            "score_llm_threshold": 0.14,
            "judge_send_threshold": 0.60,
            "judge_balance_daily_max": 48,
        },
        "safety": {
            "delivery_dedupe_hours": 10,
            "message_dedupe_recent_n": 5,
        },
    },
    "dev_verify": {
        # 改完代码后 2-5 分钟内可见效果
        "trigger": {
            "tick_interval_s0": 60,   # 1分钟
            "tick_interval_s1": 30,   # 30秒
            "tick_jitter": 0.0,       # 无抖动，精确触发
        },
        "gate": {
            "score_llm_threshold": 0.08,  # 极低门槛
            "judge_send_threshold": 0.28,
            "judge_balance_daily_max": 48,
        },
        "safety": {
            "delivery_dedupe_hours": 1,
            "message_dedupe_recent_n": 5,
        },
    },
    "quiet": {
        # 低打扰模式，比 daily 慢 3-4 倍
        "trigger": {
            "tick_interval_s0": 1800,  # 30分钟
            "tick_interval_s1": 900,   # 15分钟
            "tick_jitter": 0.3,
        },
        "gate": {
            "score_llm_threshold": 0.35,
            "judge_send_threshold": 0.75,
            "judge_balance_daily_max": 12,
        },
        "safety": {
            "delivery_dedupe_hours": 24,
            "message_dedupe_recent_n": 8,
        },
    },
}


# 策略内置参数（不对外暴露）
STRATEGY_PARAMS = {
    # 评分权重（使用旧配置的实际值）
    "score_weight_energy": 0.35,
    "score_recent_scale": 8.0,
    # 打断权重（使用旧配置的实际值）
    "interrupt_weight_reply": 0.35,
    "interrupt_weight_activity": 0.25,
    "interrupt_weight_fatigue": 0.20,
    "interrupt_activity_decay_minutes": 180.0,
    "interrupt_reply_decay_minutes": 120.0,
    "interrupt_no_reply_decay_minutes": 180.0,
    "interrupt_fatigue_window_hours": 24,
    "interrupt_fatigue_soft_cap": 4.0,
    "interrupt_random_strength": 0.16,
    "interrupt_min_floor": 0.06,
    # Judge 权重
    "judge_weight_urgency": 0.15,
    "judge_weight_balance": 0.10,
    "judge_weight_dynamics": 0.10,
    "judge_weight_information_gap": 0.25,
    "judge_weight_relevance": 0.20,
    "judge_weight_expected_impact": 0.20,
    "judge_urgency_horizon_hours": 36.0,
    # judge_balance_daily_max 已移到预设配置
    "judge_veto_balance_min": 0.1,
    "judge_veto_llm_dim_min": 2,
    # Memory retrieval 细节
    "memory_history_gate_enabled": True,
    # 去重细节
    "message_dedupe_enabled": True,
    # 其他
    "recent_chat_messages": 20,
    "interval_seconds": 1800,
    "sleep_modifier_sleeping": 0.15,
}


# Overrides 白名单
ALLOWED_OVERRIDE_KEYS = {
    "trigger": {
        "tick_interval_s0",
        "tick_interval_s1",
        "tick_jitter",
    },
    "gate": {
        "score_llm_threshold",
        "judge_send_threshold",
        "judge_balance_daily_max",
    },
    "safety": {
        "delivery_dedupe_hours",
        "message_dedupe_recent_n",
    },
}
