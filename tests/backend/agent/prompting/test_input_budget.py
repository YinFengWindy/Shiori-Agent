import pytest

from agent.prompting.input_budget import BudgetPolicy, build_input_budget
from agent.prompting.usage_anchor import InputEstimate


def budget(**overrides):
    return build_input_budget(
        **(
            {
                "context_window_tokens": 128000,
                "max_output_tokens": 64000,
                "output_tokens": 32000,
                "policy": BudgetPolicy(safety_margin_tokens=4000),
                "estimate": InputEstimate(93000, "local"),
            }
            | overrides
        )
    )


def test_output_reservation_uses_actual_cap_and_hard_limit_precedes_ratio():
    value = budget()
    assert value.output_reservation_tokens == 32000
    assert value.input_limit_tokens == 92000
    assert value.trigger_tokens == 92000
    assert value.target_tokens == 51200
    assert value.needs_trim
    smaller = budget(output_tokens=8000)
    assert smaller.input_limit_tokens == 116000
    assert smaller.trigger_tokens == 96000
    assert not smaller.needs_trim


def test_target_is_bounded_when_output_reservation_is_large():
    value = budget(max_output_tokens=120000, output_tokens=100000)
    assert (
        value.input_limit_tokens == value.target_tokens == value.trigger_tokens == 24000
    )


@pytest.mark.parametrize("output", [0, -1, 64001, 1.5, True])
def test_invalid_actual_output_is_rejected(output):
    with pytest.raises(ValueError, match="本次输出"):
        budget(output_tokens=output)


def test_no_input_space_is_an_explicit_configuration_error():
    with pytest.raises(ValueError, match="没有有效输入空间"):
        budget(context_window_tokens=36000)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_ratio": 0},
        {"target_ratio": 0.8},
        {"trigger_ratio": 1},
        {"trigger_ratio": float("nan")},
        {"safety_margin_tokens": -1},
        {"safety_margin_tokens": 1.5},
    ],
)
def test_invalid_policy_is_rejected(kwargs):
    with pytest.raises(ValueError):
        BudgetPolicy(**kwargs)
