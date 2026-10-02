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
    model_context_window: int
    output_reservation_tokens: int
    safety_margin_tokens: int
    input_limit_tokens: int
    trigger_tokens: int
    target_tokens: int
    schema_tokens: int
    model_auto_compact_token_limit: int | None = None
    trigger_ratio: float = 0.75
    target_ratio: float = 0.40

    @property
    def needs_trim(self) -> bool:
        """Compression begins at the first threshold or hard-limit boundary."""
        return self.estimate.tokens >= self.trigger_tokens


def build_input_budget(
    *,
    model_context_window: int,
    output_tokens: int,
    policy: BudgetPolicy,
    estimate: InputEstimate,
    model_auto_compact_token_limit: int | None = None,
    schema_tokens: int = 0,
) -> InputBudget:
    """Compute bounded input thresholds for one request.

    The hard limit reserves this request's actual output cap and the safety
    margin. Auto compaction starts at the registered model threshold, or the
    global trigger ratio when absent, whichever is not later than the hard
    limit; the target stays a ratio of the window under the same limit.
    """
    if type(output_tokens) is not int or output_tokens <= 0:
        raise ValueError("本次输出 token 上限必须为正整数")
    available = model_context_window - output_tokens - policy.safety_margin_tokens
    if available <= 0:
        raise ValueError("模型上下文扣除本次输出预留和安全余量后没有有效输入空间")
    threshold = (
        max(1, int(model_context_window * policy.trigger_ratio))
        if model_auto_compact_token_limit is None
        else model_auto_compact_token_limit
    )
    trigger = min(available, threshold)
    target = min(
        available, max(1, int(model_context_window * policy.target_ratio)), trigger
    )
    return InputBudget(
        estimate,
        model_context_window,
        output_tokens,
        policy.safety_margin_tokens,
        available,
        trigger,
        target,
        schema_tokens,
        model_auto_compact_token_limit,
        policy.trigger_ratio,
        policy.target_ratio,
    )
