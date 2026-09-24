from __future__ import annotations

from plugins.feishu.backend.dedupe import ExpiringIdSet


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_any_known_key_marks_a_redelivery_as_duplicate() -> None:
    seen = ExpiringIdSet()

    assert not seen.seen("event-1", "message-1")
    assert seen.seen("event-1", "message-1")
    # A resend of the same message under a new event id is still a duplicate.
    assert seen.seen("event-2", "message-1")
    assert not seen.seen("", "")


def test_ids_expire_after_the_ttl() -> None:
    clock = _Clock()
    seen = ExpiringIdSet(ttl=10, clock=clock)
    seen.seen("event-1")

    clock.now = 9.9
    assert seen.seen("event-1")
    clock.now = 10.1
    assert len(seen) == 0
    assert not seen.seen("event-1")


def test_the_set_is_bounded() -> None:
    seen = ExpiringIdSet(max_size=3)
    for index in range(10):
        seen.seen(f"event-{index}")

    assert len(seen) == 3
    assert not seen.seen("event-0")
    assert seen.seen("event-9")
