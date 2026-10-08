"""Pacing: outcome wait with a safety timeout, then the interval; busy retry."""

from plugins.desktop_pet.backend.live_pacing import OUTPUT_TIMEOUT_S, ReplyPacer


def test_pending_output_holds_until_outcome_then_interval(clock):
    pacer = ReplyPacer(clock, lambda: 5)
    assert pacer.wait_time() == (0, None)
    pacer.awaiting("r1")
    assert pacer.wait_time() == (OUTPUT_TIMEOUT_S, None)
    assert not pacer.finished("other")
    assert pacer.finished("r1")
    assert pacer.wait_time() == (5, None)
    pacer.retry_after(1)
    assert pacer.wait_time() == (1, None)


async def test_lost_outcome_is_reported_once_after_the_timeout(clock):
    pacer = ReplyPacer(clock, lambda: 0)
    pacer.awaiting("r1")
    await clock.advance(OUTPUT_TIMEOUT_S)
    assert pacer.wait_time() == (0, "r1")
    assert pacer.wait_time() == (0, None)
    assert not pacer.output_pending
