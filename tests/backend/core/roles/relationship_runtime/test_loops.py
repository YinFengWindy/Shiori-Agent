"""Relationship background maintenance handles failures at its scheduling boundary."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.roles.relationship_runtime.loops import RelationshipSnapshotLoop


@pytest.mark.asyncio
async def test_snapshot_loop_continues_other_roles_and_later_ticks(monkeypatch, caplog):
    optimizer = SimpleNamespace(
        optimize=AsyncMock(
            side_effect=[
                RuntimeError("startup provider failure"),
                {},
                RuntimeError("periodic provider failure"),
                {},
            ]
        )
    )
    roles = SimpleNamespace(
        list_roles=lambda: [SimpleNamespace(id="mira"), SimpleNamespace(id="hana")]
    )
    runtime = SimpleNamespace(read_snapshot=lambda role_id: None)
    loop = RelationshipSnapshotLoop(optimizer, role_store=roles, runtime=runtime)
    ticks = 0

    async def tick(_seconds):
        nonlocal ticks
        ticks += 1
        if ticks == 2:
            loop.stop()

    monkeypatch.setattr("core.roles.relationship_runtime.loops.asyncio.sleep", tick)
    await loop.run()
    assert [call.kwargs["role_id"] for call in optimizer.optimize.await_args_list] == [
        "mira",
        "hana",
        "mira",
        "hana",
    ]
    assert "startup provider failure" in caplog.text
    assert "periodic provider failure" in caplog.text


@pytest.mark.asyncio
async def test_snapshot_loop_does_not_swallow_cancellation():
    optimizer = SimpleNamespace(optimize=AsyncMock(side_effect=asyncio.CancelledError))
    loop = RelationshipSnapshotLoop(
        optimizer,
        role_store=SimpleNamespace(list_roles=lambda: [SimpleNamespace(id="mira")]),
        runtime=SimpleNamespace(read_snapshot=lambda role_id: None),
    )
    with pytest.raises(asyncio.CancelledError):
        await loop.run()
