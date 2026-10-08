"""Seen ids drop repeats while memory stays bounded."""

from plugins.desktop_pet.backend.live_dedupe import SeenMessages


def test_repeats_are_rejected_and_old_ids_are_forgotten():
    seen = SeenMessages(limit=2)
    assert seen.first_sight("a") and seen.first_sight("b")
    assert not seen.first_sight("a")
    assert seen.first_sight("c")
    assert seen.first_sight("a"), "the oldest id fell out of the bounded window"
