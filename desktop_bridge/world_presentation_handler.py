"""Derived World presentation queue and checkpoint adapter."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from desktop_bridge.world_presentation_assets import WorldPresentationAssetResolver
from world_simulation.performance import (
    compile_performance_plan,
    presentation_mode_for_event,
)
from world_simulation.presentation_session import WorldPresentationSession
from world_simulation.repository import WorldRepository
from world_simulation.scenes import DecisionBarrier
from world_simulation.timeline import TimelineEvent
from world_simulation.world import utc_now


class WorldPresentationHandler:
    """Own the derived scene queue without writing authoritative world facts."""

    def __init__(self, repository: WorldRepository) -> None:
        self._repository = repository

    def pause(self, world_id: str) -> dict[str, Any]:
        """Pause queue consumption while retaining the current cue cursor."""

        session = self._session(world_id)
        if session.status != "paused":
            session = replace(session, status="paused", updated_at=utc_now())
            self._repository.save_presentation_session(session)
        return self.state(world_id)

    def resume(self, world_id: str) -> dict[str, Any]:
        """Resume queue consumption without replaying completed plans."""

        state = self.state(world_id)
        if state["session"]["status"] == "paused":
            status = "playing" if state["plans"] else self._waiting_status(world_id)
            session = replace(
                self._session(world_id), status=status, updated_at=utc_now()
            )
            self._repository.save_presentation_session(session)
        return self.state(world_id)

    def checkpoint(self, world_id: str, plan_id: str, cue_index: int) -> dict[str, Any]:
        """Persist one completed cue and advance only the derived playback cursor."""

        if cue_index < 0:
            raise ValueError("cue_index 必须是非负整数")
        events = self._repository.list_events(world_id)
        scene_events = [
            event for event in events if presentation_mode_for_event(event) == "scene"
        ]
        target = next(
            (
                event
                for event in scene_events
                if compile_performance_plan(event).id == plan_id
            ),
            None,
        )
        if target is None:
            raise ValueError("找不到对应的演出计划")
        plan = compile_performance_plan(target)
        if cue_index >= len(plan.cues):
            raise ValueError("cue_index 超出演出计划范围")
        session = self._normalize_session(self._session(world_id), events)
        if target.sequence <= session.last_presented_event_sequence:
            return self.state(world_id)
        if session.status == "paused":
            raise ValueError("演出已暂停")
        next_scene = next(
            (
                event
                for event in scene_events
                if event.sequence > session.last_presented_event_sequence
            ),
            None,
        )
        if next_scene is None or target.sequence != next_scene.sequence:
            raise ValueError("演出计划必须按世界事件顺序完成")
        if session.active_plan_id not in (None, plan.id):
            raise ValueError("另一演出计划正在等待完成")
        cue = plan.cues[cue_index]
        if not cue.checkpoint and cue_index != len(plan.cues) - 1:
            raise ValueError("只能提交阻塞 cue 或计划末尾 checkpoint")
        if session.active_plan_id == plan.id and cue_index < session.active_cue_index:
            return self.state(world_id)
        if session.active_plan_id == plan.id and cue_index > session.active_cue_index:
            raise ValueError("不能跳过当前演出 cue")
        next_index = cue_index + 1
        next_session = replace(
            session,
            last_presented_event_sequence=(
                target.sequence
                if next_index >= len(plan.cues)
                else session.last_presented_event_sequence
            ),
            active_plan_id=plan.id if next_index < len(plan.cues) else None,
            active_cue_index=next_index if next_index < len(plan.cues) else 0,
            status="playing",
            updated_at=utc_now(),
        )
        self._repository.save_presentation_session(next_session)
        return self.state(world_id)

    def state(self, world_id: str) -> dict[str, Any]:
        """Derive idempotent scene plans from facts and expose the persisted cursor."""

        events = self._repository.list_events(world_id)
        barriers = self._repository.list_pending_barriers(world_id)
        session = self._normalize_session(self._session(world_id), events)
        plans = [
            compile_performance_plan(event)
            for event in events
            if event.sequence > session.last_presented_event_sequence
            and presentation_mode_for_event(event) == "scene"
        ]
        if session.active_plan_id and all(
            plan.id != session.active_plan_id for plan in plans
        ):
            session = replace(
                session,
                active_plan_id=None,
                active_cue_index=0,
                status=(
                    "playing"
                    if plans and session.status != "paused"
                    else session.status
                ),
                updated_at=utc_now(),
            )
            self._repository.save_presentation_session(session)
        elif session.status != "paused":
            desired = (
                "playing"
                if plans
                else self._waiting_status(world_id, barriers=barriers)
            )
            if session.status != desired:
                session = replace(session, status=desired, updated_at=utc_now())
                self._repository.save_presentation_session(session)
        resolver = WorldPresentationAssetResolver(
            snapshots=self._repository.list_role_snapshots(world_id),
            residents=self._repository.list_residents(world_id),
        )
        return {
            "session": session.to_bridge_dict(),
            "plans": [resolver.to_bridge_dict(plan) for plan in plans],
        }

    def _session(self, world_id: str) -> WorldPresentationSession:
        session = self._repository.get_presentation_session(world_id)
        if session is not None:
            return session
        events = self._repository.list_events(world_id)
        session = WorldPresentationSession(
            world_id=world_id,
            status="playing" if events else self._waiting_status(world_id),
        )
        self._repository.save_presentation_session(session)
        return session

    def _normalize_session(
        self,
        session: WorldPresentationSession,
        events: list[TimelineEvent],
    ) -> WorldPresentationSession:
        if session.active_plan_id or not events:
            return session
        next_scene = next(
            (
                event
                for event in events
                if event.sequence > session.last_presented_event_sequence
                and presentation_mode_for_event(event) == "scene"
            ),
            None,
        )
        target_sequence = next_scene.sequence - 1 if next_scene else events[-1].sequence
        if target_sequence <= session.last_presented_event_sequence:
            return session
        normalized = replace(
            session,
            last_presented_event_sequence=target_sequence,
            updated_at=utc_now(),
        )
        self._repository.save_presentation_session(normalized)
        return normalized

    def _waiting_status(
        self,
        world_id: str,
        *,
        barriers: list[DecisionBarrier] | None = None,
    ) -> str:
        if barriers is not None:
            return "awaiting_barrier" if barriers else "awaiting_action"
        return (
            "awaiting_barrier"
            if self._repository.list_pending_barriers(world_id)
            else "awaiting_action"
        )
