"""Desktop bridge adapter for atomic Day progression."""

from __future__ import annotations

from world_simulation.days import current_day_index, next_day_time
from world_simulation.dependencies import DependencySet
from world_simulation.proposals import BeatProposal, ProposedEvent
from world_simulation.repository import WorldRepository
from world_simulation.service import WorldSimulationService


class WorldDayHandler:
    """Own Day advancement while leaving settlement as the only fact writer."""

    def __init__(
        self,
        repository: WorldRepository,
        service: WorldSimulationService,
    ) -> None:
        self._repository = repository
        self._service = service

    def current_index(self, world_id: str) -> int:
        """Return the current Day for one world."""

        return current_day_index(self._repository.list_events(world_id))

    def advance(self, world_id: str, *, request_id: str) -> dict[str, str]:
        """Commit a compatibility Day advance without a closing player action."""

        world = self._repository.require_world(world_id)
        active_oc = self._active_oc(world_id, world.active_oc_id)
        current_day = self.current_index(world_id)
        run = self._service.start_run(
            world_id,
            kind="advance",
            request_id=f"{request_id}:run",
            expected_revision=world.revision,
            random_seed=f"{world.random_state}:{request_id}",
        )
        event = ProposedEvent(
            event_type="world.day.advanced",
            effective_at=next_day_time(world.current_time),
            day_index=current_day + 1,
            participants=(active_oc.id,),
            location=active_oc.location,
            changes={"presentation": self._next_day_presentation()},
            dependencies=DependencySet(write_facts=frozenset({"world.day.advanced"})),
        )
        proposal = self._proposal(world, run.id, run.random_seed, (event,))
        self._service.advance(proposal, request_id=request_id)
        return {"run_id": run.id}

    def complete(
        self,
        world_id: str,
        content: str,
        *,
        request_id: str,
    ) -> dict[str, str]:
        """Commit a player's closing action and the next Day atomically."""

        action = content.strip()
        if not action:
            raise ValueError("content 不能为空")
        existing = self._repository.get_idempotency_result(request_id)
        if existing is not None:
            return {"run_id": str(existing.get("run_id") or "")}
        world = self._repository.require_world(world_id)
        active_oc = self._active_oc(world_id, world.active_oc_id)
        current_day = self.current_index(world_id)
        run = self._service.start_run(
            world_id,
            kind="complete_day",
            request_id=f"{request_id}:run",
            expected_revision=world.revision,
            random_seed=f"{world.random_state}:{request_id}",
        )
        events = (
            ProposedEvent(
                event_type="scene.action.committed",
                effective_at=world.current_time,
                day_index=current_day,
                participants=(active_oc.id,),
                location=active_oc.location,
                changes={
                    "presentation": {
                        "mode": "narrative",
                        "kind": "action",
                        "content": action,
                        "speaker_name": active_oc.name,
                    }
                },
                dependencies=DependencySet(
                    write_facts=frozenset({"scene.action.committed"})
                ),
            ),
            ProposedEvent(
                event_type="world.day.advanced",
                effective_at=next_day_time(world.current_time),
                day_index=current_day + 1,
                participants=(active_oc.id,),
                location=active_oc.location,
                changes={"presentation": self._next_day_presentation()},
                dependencies=DependencySet(
                    write_facts=frozenset({"world.day.advanced"})
                ),
            ),
        )
        proposal = self._proposal(
            world,
            run.id,
            run.random_seed,
            events,
            projection_patch={"last_action": {"oc": active_oc.id, "content": action}},
        )
        result = self._service.submit_action(proposal, request_id=request_id)
        return {"run_id": str(result.get("run_id") or run.id)}

    def _active_oc(self, world_id: str, active_oc_id: str | None):
        ocs = self._repository.list_ocs(world_id)
        active = next((oc for oc in ocs if oc.id == active_oc_id), None)
        if active is None:
            raise ValueError("世界还没有可操控的 OC")
        return active

    def _proposal(
        self,
        world,
        run_id: str,
        random_seed: str,
        events: tuple[ProposedEvent, ...],
        projection_patch=None,
    ) -> BeatProposal:
        return BeatProposal(
            schema_version=1,
            proposal_id=f"proposal-{run_id}",
            proposal_type="scene_beat",
            world_id=world.id,
            world_revision=world.revision,
            run_id=run_id,
            beat_sequence=self._repository.next_event_sequence(world.id),
            provider="deterministic-world-adapter",
            model="deterministic",
            prompt_version="desktop-v1",
            random_seed=random_seed,
            source="desktop_bridge",
            events=events,
            projection_patch=projection_patch or {},
        )

    @staticmethod
    def _next_day_presentation() -> dict[str, str]:
        return {
            "mode": "narrative",
            "kind": "environment",
            "content": "新的一天开始了。",
        }
