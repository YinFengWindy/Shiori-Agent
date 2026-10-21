import pytest
from plugins.grok_bot.backend.exchange_state import read_exchange_state


def receipt(reply_to="", exchange="old"):
    return {
        "direction": "out",
        "digest": "digest",
        "exchange_id": exchange,
        "reply_to": reply_to,
        "state": "accepted",
    }


@pytest.mark.parametrize(
    "state",
    [
        {
            "exchange_id": "old",
            "count": 4,
            "messages": {"root": receipt(), "reply": receipt("root")},
        },
        {
            "exchange_id": "new",
            "count": 0,
            "messages": {"root": receipt(), "reply": receipt("root")},
        },
        {
            "exchange_id": "old",
            "count": 1,
            "messages": {"reply": receipt("missing-root")},
        },
    ],
)
def test_pruned_or_retired_legacy_chains_are_closed_instead_of_getting_smaller_budgets(
    state,
):
    migrated = read_exchange_state(state)
    assert migrated.messages
    assert all(budget.closed for budget in migrated.exchanges.values())
    assert read_exchange_state(migrated.model_dump()) == migrated


def test_cyclic_legacy_correlations_reject_without_hanging():
    with pytest.raises(ValueError, match="不能安全恢复"):
        read_exchange_state(
            {
                "exchange_id": "old",
                "count": 2,
                "messages": {"a": receipt("b"), "b": receipt("a")},
            }
        )


def test_new_state_requires_its_saved_exchange_budget():
    with pytest.raises(ValueError, match="不能安全恢复"):
        read_exchange_state({"version": 2, "messages": {"a": receipt()}})


def test_inconsistent_saved_count_cannot_reopen_a_chain_quota():
    with pytest.raises(ValueError, match="不能安全恢复"):
        read_exchange_state(
            {
                "version": 2,
                "exchanges": {"old": {"count": 0}},
                "messages": {"a": receipt()},
            }
        )
