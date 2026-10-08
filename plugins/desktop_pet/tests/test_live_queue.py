"""Queue bounds: arrival order, capacity eviction, expiry and busy requeue."""

from plugins.desktop_pet.backend.bilibili_danmaku import Danmaku
from plugins.desktop_pet.backend.live_queue import DanmakuQueue, QueuedDanmaku


def item(index: int, at: float = 0) -> QueuedDanmaku:
    return QueuedDanmaku(Danmaku(f"id-{index}", 1, "u", "t"), at)


def test_full_queue_evicts_oldest_and_requeue_keeps_the_head():
    queue = DanmakuQueue(capacity=2)
    assert queue.push(item(1)) == 0
    assert queue.push(item(2)) == 0
    assert queue.push(item(3)) == 1
    head = queue.pop()
    assert head == item(2)
    assert queue.push_front(head) == 0
    assert [queue.pop(), queue.pop(), queue.pop()] == [item(2), item(3), None]
    queue.push(item(4))
    queue.push(item(5))
    # Filled while the head was out: the requeued oldest one is the evicted one.
    assert queue.push_front(item(3)) == 1
    assert len(queue) == 2


def test_expiry_counts_from_arrival():
    queue = DanmakuQueue()
    queue.push(item(1, at=0))
    queue.push(item(2, at=10))
    assert queue.next_expiry(30) == 30
    assert queue.drop_expired(now=29.9, wait_timeout=30) == 0
    assert queue.drop_expired(now=30, wait_timeout=30) == 1
    assert queue.next_expiry(30) == 40
