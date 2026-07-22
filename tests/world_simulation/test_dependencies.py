from world_simulation.dependencies import DependencySet


def test_backfill_writes_conflict_with_later_event_reads():
    backfill = DependencySet(
        write_facts=frozenset({"relationship:a:b"}),
        write_state=frozenset({"actor:a.location"}),
    )
    later = DependencySet(
        read_facts=frozenset({"relationship:a:b"}),
        read_state=frozenset({"actor:a.location"}),
    )

    assert backfill.conflicts_with(later) == {
        "relationship:a:b",
        "actor:a.location",
    }
