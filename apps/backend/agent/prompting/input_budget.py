"""Model capacity and output reservation shared by every request boundary."""

from __future__ import annotations

from dataclasses import dataclass

from .usage_anchor import InputEstimate


@dataclass(frozen=True)
class BudgetPolicy:
    """Ratios are of model capacity; the available-input cap always wins."""

    trigger_ratio: float = 0.75
    target_ratio: float = 0.40
    safety_margin_tokens: int = 4096

    def __post_init__(self) -> None:
        if (
            any(
                type(value) not in (int, float)
                for value in (self.target_ratio, self.trigger_ratio)
            )
            or not 0 < self.target_ratio < self.trigger_ratio < 1
        ):
            raise ValueError(
                "输入预算比例必须满足 0 < target_ratio < trigger_ratio < 1"
            )
        if type(self.safety_margin_tokens) is not int or self.safety_margin_tokens < 0:
            raise ValueError("safety_margin_tokens 必须是非负整数")


@dataclass(frozen=True)
class InputBudget:
    """Complete request input, independent of model output capability or turn totals."""

    estimate: InputEstimate
    context_window_tokens: int
    output_reservation_tokens: int
    safety_margin_tokens: int
    input_limit_tokens: int
    trigger_tokens: int
    target_tokens: int
    schema_tokens: int

    @property
    def needs_trim(self) -> bool:
        """Compression begins at the first ratio or hard-limit boundary."""
        return self.estimate.tokens >= self.trigger_tokens


def build_input_budget(
    *,
    context_window_tokens: int,
    max_output_tokens: int,
    output_tokens: int,
    policy: BudgetPolicy,
    estimate: InputEstimate,
    schema_tokens: int = 0,
) -> InputBudget:
    """Validate actual output reservation and compute bounded input thresholds."""
    if type(output_tokens) is not int or not 0 < output_tokens <= max_output_tokens:
        raise ValueError("本次输出 token 上限必须为正整数，且不得超过模型最大输出能力")
    available = context_window_tokens - output_tokens - policy.safety_margin_tokens
    if available <= 0:
        raise ValueError("模型上下文扣除本次输出预留和安全余量后没有有效输入空间")
    trigger = min(available, max(1, int(context_window_tokens * policy.trigger_ratio)))
    target = min(
        available, max(1, int(context_window_tokens * policy.target_ratio)), trigger
    )
    return InputBudget(
        estimate,
        context_window_tokens,
        output_tokens,
        policy.safety_margin_tokens,
        available,
        trigger,
        target,
        schema_tokens,
    )
