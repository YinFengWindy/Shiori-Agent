"""Desktop-facing commands for the persistent shared-world bounded context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.roles import RoleStore
from desktop_bridge.world_day_handler import WorldDayHandler
from desktop_bridge.world_presentation_handler import WorldPresentationHandler
from desktop_bridge.world_snapshot_builder import WorldSnapshotBuilder
from world_simulation.actors import AutonomyPolicy, PlayerOC
from world_simulation.catalog import WorldCatalog
from world_simulation.database_manager import WorldDatabaseManager
from world_simulation.dependencies import DependencySet
from world_simulation.days import group_world_days
from world_simulation.drafts import create_world_draft
from world_simulation.errors import HistoricalConflictError
from world_simulation.performance import (
    compile_performance_plan,
    presentation_mode_for_event,
)
from world_simulation.proposals import BeatProposal, ProposedEvent
from world_simulation.repository import WorldRepository
from world_simulation.scenes import DecisionBarrier
from world_simulation.service import WorldSimulationService
from world_simulation.timeline import TimelineEvent
from world_simulation.world import (
    NativeResident,
    WorldDraft,
    WorldTemplate,
)


@dataclass(frozen=True)
class _WorldContext:
    repository: WorldRepository
    service: WorldSimulationService
    days: WorldDayHandler
    presentation: WorldPresentationHandler


class WorldSimulationHandler:
    """Translate semantic desktop commands into world-owned facts and read models."""

    def __init__(self, *, workspace: Path, role_store: RoleStore) -> None:
        self._roles = role_store
        self._catalog = WorldCatalog(workspace / "worlds" / "catalog.db")
        self._databases = WorldDatabaseManager(workspace, self._catalog)
        self._contexts: dict[str, _WorldContext] = {}
        self._snapshots = WorldSnapshotBuilder(role_store, workspace / "world_assets")
        self._shots: dict[tuple[str, str], dict[str, Any]] = {}
        self._recover_creation_intents()

    def close(self) -> None:
        """Release the dedicated world transaction store."""

        self._contexts.clear()
        self._databases.close()
        self._catalog.close()

    def handle(
        self, method: str, payload: dict[str, Any], *, request_id: str
    ) -> dict[str, Any] | None:
        """Handle a worlds.* request, returning None for unrelated bridge methods."""

        if not method.startswith("worlds."):
            return None
        if method == "worlds.list":
            return {"worlds": self._catalog.list_summaries()}
        if method == "worlds.get":
            return {"world": self._world_details(self._world_id(payload))}
        if method == "worlds.drafts.preview":
            return {"draft": self._preview_draft(payload)}
        if method == "worlds.drafts.confirm":
            return {"world": self._confirm_draft(payload, request_id=request_id)}
        if method == "worlds.ocs.add":
            return {"world": self._add_oc(payload, request_id=request_id)}
        if method == "worlds.ocs.switch":
            return {"world": self._switch_oc(payload)}
        if method == "worlds.actions.submit":
            return self._submit_action(payload, request_id=request_id)
        if method == "worlds.days.complete":
            world_id = self._world_id(payload)
            result = self._context(world_id).days.complete(
                world_id,
                self._required(payload, "content"),
                request_id=request_id,
            )
            self._refresh_summary(world_id)
            return result
        if method == "worlds.advance":
            world_id = self._world_id(payload)
            result = self._context(world_id).days.advance(
                world_id, request_id=request_id
            )
            self._refresh_summary(world_id)
            return result
        if method == "worlds.barriers.resolve":
            return {"world": self._resolve_barrier(payload, request_id=request_id)}
        if method == "worlds.timeline":
            return {"entries": self._timeline(payload)}
        if method == "worlds.copy":
            return {"world": self._copy_world(payload, request_id=request_id)}
        if method == "worlds.backfill.preview":
            return {"preview": self._preview_backfill(payload)}
        if method == "worlds.backfill.commit":
            return {"world": self._commit_backfill(payload, request_id=request_id)}
        if method == "worlds.runs.cancel":
            return {"world": self._cancel_run(payload)}
        if method == "worlds.events.catch_up":
            return self._catch_up(payload)
        if method == "worlds.presentation.pause":
            world_id = self._world_id(payload)
            return {
                "presentation": self._context(world_id).presentation.pause(world_id)
            }
        if method == "worlds.presentation.resume":
            world_id = self._world_id(payload)
            return {
                "presentation": self._context(world_id).presentation.resume(world_id)
            }
        if method == "worlds.presentation.checkpoint":
            raw_index = payload.get("cue_index")
            try:
                cue_index = int(str(raw_index).strip()) if raw_index is not None else -1
            except ValueError as exc:
                raise ValueError("cue_index 必须是非负整数") from exc
            world_id = self._world_id(payload)
            return {
                "presentation": self._context(world_id).presentation.checkpoint(
                    world_id,
                    self._required(payload, "plan_id"),
                    cue_index,
                )
            }
        if method == "worlds.shots.redraw":
            return {"shot": self._redraw_shot(payload)}
        raise ValueError(f"unknown world method: {method}")

    def _preview_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        input_data = self._creation_input(payload)
        selected_roles = [
            self._require_role(role_id) for role_id in input_data["selectedRoleIds"]
        ]
        snapshots = tuple(self._snapshots.snapshot_for(role) for role in selected_roles)
        residents = tuple(
            NativeResident(
                id=f"resident-{snapshot.source_role_id}",
                snapshot_id=snapshot.id,
                name=role.name,
                occupation=role.description or "世界原住民",
                residence=input_data["firstOc"]["entryLocation"],
                core_persona_facts=(role.system_prompt,),
                visual_identity={
                    "avatar_path": self._snapshots.source_asset_path(role.avatar)
                },
            )
            for snapshot, role in zip(snapshots, selected_roles, strict=True)
        )
        template = WorldTemplate(
            id=f"template-{uuid4().hex}",
            name=input_data["name"],
            era=input_data["tone"] or "当代",
            locations=(input_data["firstOc"]["entryLocation"],),
            initial_environment={
                "premise": input_data["premise"],
                "rules": input_data["rules"],
                "seed": input_data["seed"],
            },
            narrative_style=input_data["tone"],
        )
        draft = create_world_draft(
            owner_id="desktop-player",
            template=template,
            role_snapshots=snapshots,
            residents=residents,
            initial_time=input_data["firstOc"]["entryTime"],
            creation_metadata={"input": input_data},
        )
        self._catalog.save_draft(draft)
        return {
            "id": draft.id,
            "input": input_data,
            "nativeIdentities": [
                self._native_identity(resident, role)
                for resident, role in zip(residents, selected_roles, strict=True)
            ],
        }

    def _confirm_draft(
        self, payload: dict[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        existing_world_id = self._catalog.world_id_for_request(request_id)
        if existing_world_id is not None:
            return self._world_details(existing_world_id)
        pending_intent = self._catalog.creation_intent_for_request(request_id)
        if pending_intent is not None and self._recover_creation_intent(pending_intent):
            return self._world_details(str(pending_intent["world_id"]))
        draft_id = self._required(payload, "draft_id")
        draft = self._catalog.get_draft(draft_id)
        if draft is None:
            raise ValueError("找不到待确认的世界草案")
        identities = payload.get("native_identities")
        if not isinstance(identities, list):
            raise ValueError("原住民草案格式无效")
        edited_draft = self._apply_native_identity_edits(draft, identities)
        self._catalog.replace_draft(edited_draft)
        input_data = self._draft_input(edited_draft)
        world_id = f"world-{uuid4().hex}"
        self._catalog.register_creation_intent(
            request_id=request_id,
            world_id=world_id,
            draft_id=edited_draft.id,
            relative_db_path=self._databases.relative_path(world_id),
        )
        context = self._create_context(world_id)
        try:
            context.repository.save_draft(edited_draft)
            world = context.service.confirm_world(
                edited_draft.id,
                request_id=request_id,
                world_id=world_id,
                random_seed=input_data["seed"],
                initial_oc=self._oc_from_input(input_data["firstOc"]),
            )
            self._catalog.complete_world(
                draft_id=edited_draft.id,
                world_id=world.id,
                relative_db_path=self._databases.relative_path(world.id),
                summary=self._summary(context, world),
                request_id=request_id,
            )
        except BaseException:
            if context.repository.get_world(world_id) is None:
                self._discard_context(world_id)
            raise
        return self._world_details(world.id)

    def _add_oc(self, payload: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        world_id = self._world_id(payload)
        context = self._context(world_id)
        world = context.repository.require_world(world_id)
        oc = self._oc_from_input(self._oc_input(payload.get("oc")))
        context.service.add_oc(
            world_id,
            oc,
            entry_time=oc.identity["entry_time"],
            expected_revision=world.revision,
            request_id=request_id,
        )
        self._refresh_summary(world_id)
        return self._world_details(world_id)

    def _switch_oc(self, payload: dict[str, Any]) -> dict[str, Any]:
        world_id = self._world_id(payload)
        context = self._context(world_id)
        world = context.repository.require_world(world_id)
        context.service.switch_oc(
            world_id, self._required(payload, "oc_id"), expected_revision=world.revision
        )
        self._refresh_summary(world_id)
        return self._world_details(world_id)

    def _submit_action(
        self, payload: dict[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        world_id = self._world_id(payload)
        content = self._required(payload, "content")
        context = self._context(world_id)
        world = context.repository.require_world(world_id)
        active_oc = self._active_oc(context, world_id, world.active_oc_id)
        run = context.service.start_run(
            world_id,
            kind="action",
            request_id=f"{request_id}:run",
            expected_revision=world.revision,
            random_seed=f"{world.random_state}:{request_id}",
        )
        proposal = self._proposal(
            context=context,
            world=world,
            run_id=run.id,
            random_seed=run.random_seed,
            event_type="scene.action.committed",
            effective_at=world.current_time,
            day_index=context.days.current_index(world_id),
            participants=(active_oc.id,),
            location=active_oc.location,
            presentation={
                "mode": "narrative",
                "kind": "action",
                "content": content,
                "speaker_name": active_oc.name,
            },
            projection_patch={"last_action": {"oc": active_oc.id, "content": content}},
        )
        context.service.submit_action(proposal, request_id=request_id)
        self._refresh_summary(world_id)
        return {"run_id": run.id}

    def _resolve_barrier(
        self, payload: dict[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        world_id = self._world_id(payload)
        context = self._context(world_id)
        world = context.repository.require_world(world_id)
        barrier = context.repository.get_barrier(
            world_id, self._required(payload, "barrier_id")
        )
        if barrier is None:
            raise ValueError("待决事件已经不存在")
        choice_id = self._required(payload, "choice_id")
        option = next(
            (item for item in barrier.options if str(item.get("id")) == choice_id), None
        )
        if option is None:
            raise ValueError("不是这个待决事件的选择")
        run = context.service.start_run(
            world_id,
            kind="barrier_resolution",
            request_id=f"{request_id}:run",
            expected_revision=world.revision,
            random_seed=f"{world.random_state}:{request_id}",
        )
        proposal = self._proposal(
            context=context,
            world=world,
            run_id=run.id,
            random_seed=run.random_seed,
            event_type="decision.resolved",
            effective_at=barrier.effective_at,
            participants=(barrier.oc_id,),
            presentation={
                "kind": "action",
                "content": str(option.get("label") or "作出了决定"),
            },
        )
        context.service.resolve_barrier(
            world_id,
            barrier.id,
            proposal,
            request_id=request_id,
            resolution={"choice_id": choice_id, "label": option.get("label", "")},
        )
        self._refresh_summary(world_id)
        return self._world_details(world_id)

    def _timeline(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        world_id = self._world_id(payload)
        perspective = str(payload.get("perspective") or "omniscient")
        oc_id = str(payload.get("oc_id") or "")
        context = self._context(world_id)
        entries = []
        for event in context.repository.list_events(world_id):
            known_to = (
                set(event.visibility.get("known_to", ()))
                if isinstance(event.visibility, dict)
                else set()
            )
            if perspective == "known" and oc_id and known_to and oc_id not in known_to:
                continue
            entries.append(
                self._timeline_entry(
                    context,
                    event,
                    visibility="known" if known_to else "omniscient",
                )
            )
        return entries

    def _copy_world(
        self, payload: dict[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        existing_world_id = self._catalog.world_id_for_request(request_id)
        if existing_world_id is not None:
            return self._world_details(existing_world_id)
        pending_intent = self._catalog.creation_intent_for_request(request_id)
        if pending_intent is not None and self._recover_creation_intent(pending_intent):
            return self._world_details(str(pending_intent["world_id"]))
        source_world_id = self._world_id(payload)
        source_context = self._context(source_world_id)
        target_world_id = f"world-{uuid4().hex}"
        self._catalog.register_creation_intent(
            request_id=request_id,
            world_id=target_world_id,
            draft_id=None,
            relative_db_path=self._databases.relative_path(target_world_id),
        )
        target_context = self._create_context(target_world_id)
        try:
            world = source_context.service.copy_world(
                source_world_id,
                self._required(payload, "anchor_id"),
                request_id=request_id,
                new_world_id=target_world_id,
                target_repository=target_context.repository,
            )
            self._catalog.complete_world(
                draft_id=None,
                world_id=world.id,
                relative_db_path=self._databases.relative_path(world.id),
                summary=self._summary(target_context, world),
                request_id=request_id,
            )
        except BaseException:
            if target_context.repository.get_world(target_world_id) is None:
                self._discard_context(target_world_id)
            raise
        return self._world_details(world.id)

    def _preview_backfill(self, payload: dict[str, Any]) -> dict[str, Any]:
        world_id = self._world_id(payload)
        anchor_id = self._required(payload, "anchor_id")
        context = self._context(world_id)
        anchor = context.repository.get_event(world_id, anchor_id)
        if anchor is None:
            raise ValueError("找不到入场锚点")
        oc = self._oc_input(payload.get("oc"))
        conflicts = self._backfill_conflicts(context, world_id, oc["entryTime"])
        return {
            "anchorId": anchor.id,
            "oc": oc,
            "stages": [
                {
                    "title": "过去经历",
                    "summary": "日常经历将作为私有历史补入。",
                    "playable": False,
                },
                {
                    "title": "入场时刻",
                    "summary": "重要转折会在共享世界中成为可玩场景。",
                    "playable": True,
                },
            ],
            "conflicts": conflicts,
            "allowed": not conflicts,
        }

    def _commit_backfill(
        self, payload: dict[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        world_id = self._world_id(payload)
        preview = payload.get("preview")
        if not isinstance(preview, dict):
            raise ValueError("历史补写预览格式无效")
        anchor_id = self._required(preview, "anchorId")
        context = self._context(world_id)
        if context.repository.get_event(world_id, anchor_id) is None:
            raise ValueError("历史入场锚点已经不存在")
        oc = self._oc_from_input(self._oc_input(preview.get("oc")))
        world = context.repository.require_world(world_id)
        context.service.add_oc(
            world_id,
            oc,
            entry_time=oc.identity["entry_time"],
            expected_revision=world.revision,
            request_id=request_id,
        )
        self._refresh_summary(world_id)
        return self._world_details(world_id)

    def _cancel_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        world_id = self._world_id(payload)
        context = self._context(world_id)
        # A run that already committed is intentionally not rolled back.
        run = next(
            (
                item
                for item in context.repository.list_runs(world_id)
                if item.status not in {"completed", "failed", "cancelled"}
            ),
            None,
        )
        if run is not None:
            context.service.cancel_run(run.id)
        return self._world_details(world_id)

    def _catch_up(self, payload: dict[str, Any]) -> dict[str, Any]:
        world_id = self._world_id(payload)
        context = self._context(world_id)
        cursor = int(str(payload.get("cursor") or "0").strip() or 0)
        messages = context.repository.list_outbox(world_id, after_sequence=cursor)
        beats = [
            self._beat(message["payload"].get("event", {}), int(message["sequence"]))
            for message in messages
        ]
        next_cursor = str(messages[-1]["sequence"] if messages else cursor)
        world = self._world_details(world_id)
        return {
            "cursor": next_cursor,
            "beats": beats,
            "world": world,
            "presentation": world["presentation"],
        }

    def _redraw_shot(self, payload: dict[str, Any]) -> dict[str, Any]:
        world_id = self._world_id(payload)
        shot_id = self._required(payload, "shot_id")
        existing = self._shots.get(
            (world_id, shot_id), {"id": shot_id, "prompt": "当前场景", "assets": []}
        )
        shot = {**existing, "status": "developing"}
        self._shots[(world_id, shot_id)] = shot
        return shot

    def _world_details(self, world_id: str) -> dict[str, Any]:
        context = self._context(world_id)
        world = context.repository.require_world(world_id)
        ocs = context.repository.list_ocs(world_id)
        residents = context.repository.list_residents(world_id)
        barriers = context.repository.list_pending_barriers(world_id)
        events = context.repository.list_events(world_id)
        active_oc = next(
            (oc for oc in ocs if oc.id == world.active_oc_id), ocs[0] if ocs else None
        )
        beats = [
            self._beat(event.to_dict(), index + 1) for index, event in enumerate(events)
        ]
        current_day_index = context.days.current_index(world_id)
        days = [
            {
                "dayIndex": group.day_index,
                "title": f"Day {group.day_index}",
                "status": group.status,
                "events": [
                    beat
                    for beat, event in zip(beats, events, strict=True)
                    if event in group.events
                ],
            }
            for group in group_world_days(events)
        ]
        return {
            **self._summary(context, world),
            "currentDayIndex": current_day_index,
            "days": days,
            "ocs": [
                self._oc_view(oc, active=oc.id == world.active_oc_id) for oc in ocs
            ],
            "scene": {
                "title": f"{world.template_snapshot.get('name', '世界')}的此刻",
                "location": active_oc.location if active_oc else "未知地点",
                "timeLabel": world.current_time,
                "participants": [
                    {
                        "id": oc.id,
                        "name": oc.name,
                        "role": (
                            "controlled_oc"
                            if oc.id == world.active_oc_id
                            else "observer"
                        ),
                    }
                    for oc in ocs
                ],
                "beats": beats,
                "actionPrompt": (
                    f"{active_oc.name}准备怎么做？" if active_oc else "先创建一位 OC。"
                ),
                "opportunities": [],
                "barriers": [
                    self._barrier_view(context, item, ocs) for item in barriers
                ],
            },
            "relatedCharacters": [
                {
                    "id": resident.id,
                    "name": resident.name,
                    "relationship": resident.occupation or "世界原住民",
                    "avatarUrl": resident.visual_identity.get("avatar_path"),
                }
                for resident in residents
            ],
            "performance": {
                "active": bool(beats),
                "label": "观看现场演出",
                "canCancel": False,
            },
            "presentation": context.presentation.state(world_id),
        }

    def _summary(self, context: _WorldContext, world: Any) -> dict[str, Any]:
        environment = world.template_snapshot.get("initial_environment", {})
        return {
            "id": world.id,
            "name": world.template_snapshot.get("name", "未命名世界"),
            "premise": environment.get("premise", ""),
            "currentTimeLabel": world.current_time,
            "currentDayIndex": context.days.current_index(world.id),
            "activeOcId": world.active_oc_id,
            "status": (
                "barrier"
                if context.repository.list_pending_barriers(world.id)
                else "action_required"
            ),
        }

    def _proposal(
        self,
        *,
        context: _WorldContext,
        world: Any,
        run_id: str,
        random_seed: str,
        event_type: str,
        effective_at: str,
        participants: tuple[str, ...],
        location: str = "",
        presentation: dict[str, Any],
        projection_patch: dict[str, Any] | None = None,
        day_index: int | None = None,
    ) -> BeatProposal:
        event = ProposedEvent(
            event_type=event_type,
            effective_at=effective_at,
            day_index=day_index or context.days.current_index(world.id),
            participants=participants,
            location=location,
            changes={"presentation": presentation},
            dependencies=DependencySet(write_facts=frozenset({event_type})),
        )
        return self._proposal_from_events(
            context=context,
            world=world,
            run_id=run_id,
            random_seed=random_seed,
            events=(event,),
            projection_patch=projection_patch,
        )

    def _proposal_from_events(
        self,
        *,
        context: _WorldContext,
        world: Any,
        run_id: str,
        random_seed: str,
        events: tuple[ProposedEvent, ...],
        projection_patch: dict[str, Any] | None = None,
    ) -> BeatProposal:
        """Build one settlement envelope for one or more Day events."""

        return BeatProposal(
            schema_version=1,
            proposal_id=f"proposal-{uuid4().hex}",
            proposal_type="scene_beat",
            world_id=world.id,
            world_revision=world.revision,
            run_id=run_id,
            beat_sequence=context.repository.next_event_sequence(world.id),
            provider="deterministic-world-adapter",
            model="deterministic",
            prompt_version="desktop-v1",
            random_seed=random_seed,
            source="desktop_bridge",
            events=events,
            projection_patch=projection_patch or {},
        )

    def _beat(self, event: dict[str, Any], order: int) -> dict[str, Any]:
        changes = (
            event.get("changes", {}) if isinstance(event.get("changes"), dict) else {}
        )
        presentation = (
            changes.get("presentation", {})
            if isinstance(changes.get("presentation"), dict)
            else {}
        )
        event_type = str(event.get("event_type") or "world.event")
        mode = presentation_mode_for_event(event)
        beat = {
            "id": str(event.get("id") or f"beat-{order}"),
            "order": order,
            "dayIndex": int(event.get("day_index") or 1),
            "timeLabel": str(event.get("effective_at") or ""),
            "speakerName": presentation.get("speaker_name"),
            "kind": presentation.get("kind", "environment"),
            "content": presentation.get("content", self._event_summary(event_type)),
            "presentationMode": mode,
            "isCritical": event_type.startswith("decision."),
        }
        if mode == "scene":
            beat["performancePlan"] = compile_performance_plan(event).to_bridge_dict()
        return beat

    def _timeline_entry(
        self, context: _WorldContext, event: TimelineEvent, *, visibility: str
    ) -> dict[str, Any]:
        return {
            "id": event.id,
            "dayIndex": event.day_index,
            "timeLabel": event.effective_at,
            "title": self._event_title(event.event_type),
            "summary": self._beat(event.to_dict(), event.sequence)["content"],
            "visibility": visibility,
            "involvedNames": self._participant_names(
                context, event.world_id, event.participants
            ),
            "canCopy": True,
            "canEnter": True,
        }

    @staticmethod
    def _event_title(event_type: str) -> str:
        return {
            "world.created": "世界开启",
            "player_oc.joined": "新的入场",
            "player_oc.backfilled": "补入过去",
            "scene.action.committed": "行动",
            "world.time.advanced": "世界继续流动",
            "world.day.advanced": "新的一天",
            "decision.resolved": "做出了决定",
        }.get(event_type, "世界事件")

    @staticmethod
    def _event_summary(event_type: str) -> str:
        return {
            "world.created": "世界的既定事实从这一刻开始。",
            "player_oc.joined": "一位新的 OC 来到世界。",
            "player_oc.backfilled": "新的经历被安全地补入过去。",
        }.get(event_type, "世界发生了新的变化。")

    def _native_identity(self, resident: NativeResident, role: Any) -> dict[str, Any]:
        return {
            "roleId": role.id,
            "roleName": role.name,
            "nativeName": resident.name,
            "identity": resident.occupation,
            "history": "在世界开始前已经拥有自己的生活。",
            "relationships": "",
            "accepted": True,
        }

    def _apply_native_identity_edits(
        self, draft: WorldDraft, identities: list[Any]
    ) -> WorldDraft:
        edits = {
            str(item.get("roleId")): item
            for item in identities
            if isinstance(item, dict) and bool(item.get("accepted"))
        }
        if len(edits) != len(draft.residents):
            raise ValueError("请确认所有原住民草案")
        residents = []
        for resident in draft.residents:
            source_role_id = next(
                snapshot.source_role_id
                for snapshot in draft.role_snapshots
                if snapshot.id == resident.snapshot_id
            )
            edit = edits.get(source_role_id)
            if edit is None:
                raise ValueError("原住民草案与世界不一致")
            residents.append(
                replace(
                    resident,
                    name=self._required(edit, "nativeName"),
                    occupation=self._required(edit, "identity"),
                    prior_experiences=({"summary": self._required(edit, "history")},),
                )
            )
        return replace(draft, residents=tuple(residents))

    def _backfill_conflicts(
        self, context: _WorldContext, world_id: str, entry_time: str
    ) -> list[str]:
        try:
            context.service._validate_backfill(
                world_id,
                entry_time,
                DependencySet(write_facts=frozenset({"oc:private_history"})),
            )
        except HistoricalConflictError:
            return ["这段经历会改变已经结算的公共因果。请从更早的节点创建世界副本。"]
        return []

    def _oc_from_input(self, value: dict[str, str]) -> PlayerOC:
        return PlayerOC(
            id=f"oc-{uuid4().hex}",
            name=value["name"],
            persona={"identity": value["identity"]},
            identity={
                "description": value["identity"],
                "entry_time": value["entryTime"],
            },
            primary_goal=value["primaryGoal"],
            location=value["entryLocation"],
            autonomy=AutonomyPolicy(allow_optional_scenes=True),
        )

    def _oc_view(self, oc: PlayerOC, *, active: bool) -> dict[str, Any]:
        return {
            "id": oc.id,
            "name": oc.name,
            "identity": str(oc.identity.get("description") or ""),
            "location": oc.location,
            "primaryGoal": oc.primary_goal,
            "constraints": list(oc.behavior_constraints),
            "autonomy": "guided" if oc.autonomy.allow_optional_scenes else "manual",
            "isActive": active,
        }

    def _barrier_view(
        self,
        context: _WorldContext,
        barrier: DecisionBarrier,
        ocs: list[PlayerOC],
    ) -> dict[str, Any]:
        return {
            "id": barrier.id,
            "title": barrier.reason,
            "context": barrier.reason,
            "affectedOcNames": self._participant_names(
                context, barrier.world_id, (barrier.oc_id,)
            ),
            "choices": [
                {
                    "id": str(item.get("id", "")),
                    "label": str(item.get("label", "")),
                    "consequence": item.get("consequence"),
                }
                for item in barrier.options
            ],
        }

    def _participant_names(
        self,
        context: _WorldContext,
        world_id: str,
        participants: tuple[str, ...],
    ) -> list[str]:
        names = {oc.id: oc.name for oc in context.repository.list_ocs(world_id)}
        names.update(
            {
                resident.id: resident.name
                for resident in context.repository.list_residents(world_id)
            }
        )
        return [names[item] for item in participants if item in names]

    def _active_oc(
        self, context: _WorldContext, world_id: str, oc_id: str | None
    ) -> PlayerOC:
        oc = next(
            (
                item
                for item in context.repository.list_ocs(world_id)
                if item.id == oc_id
            ),
            None,
        )
        if oc is None:
            raise ValueError("请先选择一位当前 OC")
        return oc

    def _context(self, world_id: str) -> _WorldContext:
        context = self._contexts.get(world_id)
        if context is not None:
            return context
        return self._bind_context(world_id, self._databases.open(world_id))

    def _recover_creation_intents(self) -> None:
        """Reconcile committed world databases left behind by a crashed catalog write."""

        for intent in self._catalog.pending_creation_intents():
            self._recover_creation_intent(intent)

    def _recover_creation_intent(self, intent: dict[str, Any]) -> bool:
        world_id = str(intent["world_id"])
        repository = self._databases.open_for_recovery(
            world_id, str(intent["relative_db_path"])
        )
        if repository is None:
            self._catalog.discard_creation_intent(str(intent["request_id"]))
            self._databases.discard_unregistered(world_id)
            return False
        self._bind_context(world_id, repository)
        self._catalog.complete_world(
            draft_id=(
                str(intent["draft_id"]) if intent.get("draft_id") is not None else None
            ),
            world_id=world_id,
            relative_db_path=str(intent["relative_db_path"]),
            summary={},
            request_id=str(intent["request_id"]),
        )
        self._refresh_summary(world_id)
        return True

    def _create_context(self, world_id: str) -> _WorldContext:
        return self._bind_context(world_id, self._databases.create(world_id))

    def _bind_context(
        self, world_id: str, repository: WorldRepository
    ) -> _WorldContext:
        service = WorldSimulationService(repository)
        context = _WorldContext(
            repository=repository,
            service=service,
            days=WorldDayHandler(repository, service),
            presentation=WorldPresentationHandler(repository),
        )
        self._contexts[world_id] = context
        return context

    def _discard_context(self, world_id: str) -> None:
        self._contexts.pop(world_id, None)
        self._databases.discard_unregistered(world_id)

    def _refresh_summary(self, world_id: str) -> None:
        context = self._context(world_id)
        world = context.repository.require_world(world_id)
        self._catalog.update_summary(world_id, self._summary(context, world))

    def _require_role(self, role_id: str) -> Any:
        role = self._roles.get_role(role_id)
        if role is None:
            raise ValueError("选择的角色已经不存在")
        return role

    def _draft_input(self, draft: WorldDraft) -> dict[str, Any]:
        value = draft.creation_metadata.get("input")
        if not isinstance(value, dict):
            raise ValueError("世界草案缺少首位 OC 信息")
        return self._creation_input(value)

    def _creation_input(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("世界创建信息格式无效")
        oc = self._oc_input(payload.get("firstOc"))
        selected = payload.get("selectedRoleIds")
        if not isinstance(selected, list):
            raise ValueError("原住民选择格式无效")
        return {
            "name": self._required(payload, "name"),
            "premise": self._required(payload, "premise"),
            "rules": str(payload.get("rules") or ""),
            "tone": str(payload.get("tone") or ""),
            "selectedRoleIds": [str(item) for item in selected if str(item).strip()],
            "seed": self._required(payload, "seed"),
            "firstOc": oc,
        }

    def _oc_input(self, payload: Any) -> dict[str, str]:
        if not isinstance(payload, dict):
            raise ValueError("OC 信息格式无效")
        entry_time = self._required(payload, "entryTime")
        try:
            parsed = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("入场时间无效") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return {
            "name": self._required(payload, "name"),
            "identity": self._required(payload, "identity"),
            "entryTime": parsed.astimezone(timezone.utc).isoformat(),
            "entryLocation": self._required(payload, "entryLocation"),
            "primaryGoal": str(payload.get("primaryGoal") or ""),
        }

    @staticmethod
    def _required(payload: dict[str, Any], field: str) -> str:
        value = str(payload.get(field) or "").strip()
        if not value:
            raise ValueError(f"{field} 不能为空")
        return value

    def _world_id(self, payload: dict[str, Any]) -> str:
        return self._required(payload, "world_id")
