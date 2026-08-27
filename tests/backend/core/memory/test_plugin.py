from core.memory.plugin import DisabledMemoryEngine


def test_disabled_memory_engine_invalidates_no_memories() -> None:
    assert DisabledMemoryEngine().invalidate_role_memories("mira") == 0
