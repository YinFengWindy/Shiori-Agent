from plugins.telegram.backend.channel.dedupe import MessageDeduper


def test_message_deduper_evicts_oldest_keys():
    deduper = MessageDeduper(max_size=2)

    assert deduper.seen("a") is False
    assert deduper.seen("b") is False
    assert deduper.seen("a") is True
    assert deduper.seen("c") is False
    assert deduper.seen("a") is False
