"""``on_published``: callbacks run when their own generation is published."""

from __future__ import annotations

import pytest

from infra.process.resources import ProcessResourceOwner
from shiori_sdk.kernel import Scope


@pytest.mark.asyncio
async def test_publication_runs_its_generation_and_drops_a_discarded_one() -> None:
    owner = ProcessResourceOwner()
    owner.publish("g1")
    calls: list[str] = []
    current = owner.for_plugin("g1", "probe", Scope("probe"))
    candidate = owner.for_plugin("g2", "probe", Scope("probe"))
    discarded = owner.for_plugin("g3", "probe", Scope("probe"))

    # Already published: runs before on_published returns.
    _ = current.on_published(lambda: calls.append("g1"))
    _ = candidate.on_published(lambda: calls.append("g2"))
    _ = discarded.on_published(lambda: calls.append("g3"))
    assert calls == ["g1"]

    # A discarded candidate's attachment closes; its callback never runs.
    await discarded.close()
    owner.publish("g2")
    owner.publish("g3")
    assert calls == ["g1", "g2"]
    await owner.close()
