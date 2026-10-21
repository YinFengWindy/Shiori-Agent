import pytest
from shiori_sdk.testing.storage import FakeKV
from plugins.grok_bot.backend.exchange import ExchangeJournal, QUIET_RESET_SECONDS
from plugins.grok_bot.backend.protocol import BotMessage, CallbackError


def test_new_ids_or_missing_reply_do_not_reset_budget_and_restart_preserves_it():
    kv = FakeKV()
    journal = ExchangeJournal(kv, "connection", "bot", clock=lambda: 100.0)
    for index in range(4):
        message = BotMessage(str(index), "hi")
        assert journal.begin(message, "out", 4)
        journal.finish(message.message_id, "accepted", "accepted")
    restored = ExchangeJournal(kv, "connection", "bot", clock=lambda: 101.0)
    with pytest.raises(CallbackError, match="上限"):
        restored.begin(BotMessage("new-id", "hi"), "in", 4)
    restored.reset()
    assert restored.begin(BotMessage("new-id", "hi"), "in", 4)


def test_duplicate_conflict_correlation_and_unknown_send_never_replay():
    kv = FakeKV()
    journal = ExchangeJournal(kv, "c", "b")
    original = BotMessage("sent", "hello")
    journal.begin(original, "out", 12)
    restored = ExchangeJournal(kv, "c", "b")
    assert restored.state.messages["sent"].state == "uncertain"
    assert "不确定" in restored.state.last_status
    assert ExchangeJournal(kv, "c", "b").state.last_status == restored.state.last_status
    assert restored.pending() == []
    with pytest.raises(CallbackError, match="不确定"):
        restored.begin(original, "out", 12)
    assert restored.begin(BotMessage("reply", "yes", "sent"), "in", 12)
    assert not restored.begin(BotMessage("reply", "yes", "sent"), "in", 12)
    with pytest.raises(CallbackError, match="其他内容"):
        restored.begin(BotMessage("reply", "changed", "sent"), "in", 12)
    with pytest.raises(CallbackError, match="不存在"):
        restored.begin(BotMessage("wrong", "hi", "foreign"), "in", 12)


def test_quiet_period_resets_only_an_uncorrelated_new_exchange():
    now = 100.0
    journal = ExchangeJournal(FakeKV(), "c", "b", clock=lambda: now)
    journal.begin(BotMessage("a", "hi"), "out", 2)
    journal.finish("a", "accepted", "accepted")
    journal.begin(BotMessage("b", "hi", "a"), "in", 2)
    journal.finish("b", "complete", "done")
    now += QUIET_RESET_SECONDS + 1
    with pytest.raises(CallbackError, match="上限"):
        journal.begin(BotMessage("c", "hi", "a"), "in", 2)
    assert journal.begin(BotMessage("d", "new"), "in", 2)
    assert journal.state.count == 1
