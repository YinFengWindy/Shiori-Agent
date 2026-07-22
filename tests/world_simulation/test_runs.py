import pytest

from world_simulation.errors import InvalidRunTransitionError
from world_simulation.runs import WorldRun


def test_run_state_machine_rejects_skipping_settlement():
    run = WorldRun(
        id="run-1",
        request_id="request-1",
        world_id="world-1",
        kind="action",
        starting_revision=1,
        random_seed="seed",
    )

    with pytest.raises(InvalidRunTransitionError):
        run.transition("committed")

    committed = (
        run.transition("running")
        .transition("settling")
        .transition("committed", last_committed_revision=2)
    )
    assert committed.last_committed_revision == 2
