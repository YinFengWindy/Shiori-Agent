import pytest
from shiori_sdk.testing.storage import FakeKV
from plugins.grok_bot.backend.exchange import ExchangeJournal
from plugins.grok_bot.backend.protocol import BotMessage, CallbackError


def deliver(journal, message_id, direction, reply_to="", limit=12):
    message = BotMessage(message_id, "hello", reply_to)
    assert journal.begin(message, direction, limit)
    journal.finish(message_id, "accepted" if direction == "out" else "complete", "done")


def test_interleaved_chains_keep_independent_budgets_through_restart():
    kv = FakeKV()
    journal = ExchangeJournal(kv, "c", "b")
    for index in range(8):
        deliver(
            journal,
            f"a{index}",
            "in" if index % 2 == 0 else "out",
            f"a{index - 1}" if index else "",
        )
    deliver(journal, "b0", "out")
    deliver(journal, "a8", "in", "a7")
    deliver(journal, "a9", "out", "a8")
    deliver(journal, "b1", "in", "b0")
    journal = ExchangeJournal(kv, "c", "b")
    assert {key: budget.count for key, budget in journal.state.exchanges.items()} == {
        "a0": 10,
        "b0": 2,
    }
    deliver(journal, "b2", "out", "b1")
    deliver(journal, "a10", "in", "a9")
    deliver(journal, "a11", "out", "a10")
    with pytest.raises(CallbackError, match="上限"):
        journal.begin(BotMessage("a12", "hello", "a11"), "in", 12)
    assert not journal.begin(BotMessage("a11", "hello", "a10"), "out", 12)
    deliver(journal, "b3", "in", "b2")
    assert journal.state.exchanges["a0"].count == 12
    assert journal.state.exchanges["b0"].count == 4


def test_legacy_active_account_budget_becomes_two_chains_without_losing_receipts():
    kv = FakeKV()
    original = ExchangeJournal(kv, "c", "b")
    for root, length in (("a", 10), ("b", 2)):
        for index in range(length):
            deliver(
                original,
                f"{root}{index}",
                "out" if index % 2 == 0 else "in",
                f"{root}{index - 1}" if index else "",
            )
    legacy_messages = {
        key: {**receipt.model_dump(), "exchange_id": "old"}
        for key, receipt in original.state.messages.items()
    }
    kv.set(
        "exchange:c:b",
        {
            "exchange_id": "old",
            "count": 12,
            "last_activity": 100.0,
            "messages": legacy_messages,
        },
    )
    migrated = ExchangeJournal(kv, "c", "b")
    deliver(migrated, "b2", "out", "b1")
    assert migrated.state.exchanges["a0"].count == 10
    assert migrated.state.exchanges["b0"].count == 3
    assert not migrated.begin(BotMessage("a0", "hello"), "out", 12)
    assert ExchangeJournal(kv, "c", "b").state == migrated.state


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


def test_retention_expires_whole_settled_chains_without_reducing_live_budget(
    monkeypatch,
):
    monkeypatch.setattr("plugins.grok_bot.backend.exchange.MAX_RECORDS", 6)
    kv = FakeKV()
    journal = ExchangeJournal(kv, "c", "b")
    for root in ("a", "b", "c"):
        deliver(journal, root, "out")
        deliver(journal, root + "-reply", "in", root)
    deliver(journal, "b-third", "out", "b-reply")
    assert "a" not in journal.state.exchanges
    assert "a-reply" not in journal.state.messages
    with pytest.raises(CallbackError, match="不存在"):
        journal.begin(BotMessage("late", "hello", "a"), "in", 12)
    assert journal.state.exchanges["b"].count == 3
    journal = ExchangeJournal(kv, "c", "b")
    deliver(journal, "b-fourth", "in", "b-third", limit=4)
    with pytest.raises(CallbackError, match="上限"):
        journal.begin(BotMessage("b-fifth", "hello", "b-fourth"), "out", 4)


def test_retention_preserves_pending_and_uncertain_work_and_refuses_overflow(
    monkeypatch,
):
    monkeypatch.setattr("plugins.grok_bot.backend.exchange.MAX_RECORDS", 3)
    journal = ExchangeJournal(FakeKV(), "c", "b")
    journal.begin(BotMessage("queued", "hello"), "in", 12)
    journal.begin(BotMessage("sending", "hello"), "out", 12)
    journal.begin(BotMessage("uncertain", "hello"), "out", 12)
    journal.finish("uncertain", "uncertain", "unknown")
    with pytest.raises(CallbackError, match="待处理交流"):
        journal.begin(BotMessage("new", "hello"), "out", 12)
    assert set(journal.state.messages) == {"queued", "sending", "uncertain"}
    assert [message.message_id for message in journal.pending()] == ["queued"]


def test_busy_chain_does_not_consume_an_independent_roots_admission_budget():
    journal = ExchangeJournal(FakeKV(), "c", "b")
    journal.begin(BotMessage("root", "hello"), "in", 100)
    for index in range(15):
        journal.begin(BotMessage(f"pending{index}", "reply", "root"), "out", 100)
    with pytest.raises(CallbackError, match="待处理消息"):
        journal.begin(BotMessage("more", "reply", "root"), "out", 100)
    assert journal.begin(BotMessage("independent", "new topic"), "out", 100)
