"""Durable replay facade for committed world notifications."""

from __future__ import annotations

from world_simulation.repository import WorldRepository


class WorldOutbox:
    """Expose ordered replay and monotonic consumer acknowledgement."""

    def __init__(self, repository: WorldRepository) -> None:
        self._repository = repository

    def catch_up(
        self, world_id: str, *, after_sequence: int = 0, limit: int = 100
    ) -> list[dict[str, object]]:
        """Read durable notifications after an explicit cursor."""

        return self._repository.list_outbox(
            world_id, after_sequence=after_sequence, limit=limit
        )

    def acknowledge(self, consumer_id: str, world_id: str, sequence: int) -> None:
        """Persist a consumer's progress without moving it backwards."""

        self._repository.acknowledge_outbox(consumer_id, world_id, sequence)

    def resume(self, consumer_id: str, world_id: str) -> list[dict[str, object]]:
        """Replay from the consumer's last durable acknowledgement."""

        cursor = self._repository.consumer_cursor(consumer_id, world_id)
        return self.catch_up(world_id, after_sequence=cursor)
