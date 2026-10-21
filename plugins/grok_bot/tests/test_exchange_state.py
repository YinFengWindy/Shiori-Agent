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
