"""Desktop-facing commands for the persistent shared-world bounded context."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.roles import RoleStore
from world_simulation.actors import AutonomyPolicy, PlayerOC
from world_simulation.dependencies import DependencySet
from world_simulation.errors import HistoricalConflictError
from world_simulation.proposals import BeatProposal, ProposedEvent
from world_simulation.repository import WorldRepository
from world_simulation.scenes import DecisionBarrier
from world_simulation.service import WorldSimulationService
from world_simulation.timeline import TimelineEvent
from world_simulation.world import NativeResident, RoleTemplateSnapshot, WorldDraft, WorldTemplate


class WorldSimulationHandler:
    """Translate semantic desktop commands into world-owned facts and read models."""

    def __init__(self, *, workspace: Path, role_store: RoleStore) -> None:
        self._roles = role_store
        self._repository = WorldRepository(workspace / "worlds.db")
        self._service = WorldSimulationService(self._repository)
        self._shots: dict[tuple[str, str], dict[str, Any]] = {}

    def close(self) -> None:
        """Release the dedicated world transaction store."""

        self._repository.close()

    def handle(self, method: str, payload: dict[str, Any], *, request_id: str) -> dict[str, Any] | None:
        """Handle a worlds.* request, returning None for unrelated bridge methods."""

        if not method.startswith("worlds."):
            return None
        if method == "worlds.list":
            return {"worlds": [self._summary(world) for world in self._repository.list_worlds()]}
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
        if method == "worlds.advance":
            return self._advance(payload, request_id=request_id)
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
        if method == "worlds.shots.redraw":
            return {"shot": self._redraw_shot(payload)}
        raise ValueError(f"unknown world method: {method}")

    def _preview_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        input_data = self._creation_input(payload)
        selected_roles = [self._require_role(role_id) for role_id in input_data["selectedRoleIds"]]
        snapshots = tuple(self._snapshot_for(role) for role in selected_roles)
        residents = tuple(
            NativeResident(
                id=f"resident-{snapshot.source_role_id}",
                snapshot_id=snapshot.id,
                name=role.name,
                occupation=role.description or "世界原住民",
                residence=input_data["firstOc"]["entryLocation"],
                core_persona_facts=(role.system_prompt,),
                visual_identity={"avatar_path": self._asset_path(role.avatar)},
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
        draft = self._service.create_draft(
            owner_id="desktop-player",
            template=template,
            role_snapshots=snapshots,
            residents=residents,
            initial_time=input_data["firstOc"]["entryTime"],
            creation_metadata={"input": input_data},
        )
        return {
            "id": draft.id,
            "input": input_data,
            "nativeIdentities": [self._native_identity(resident, role) for resident, role in zip(residents, selected_roles, strict=True)],
        }

    def _confirm_draft(self, payload: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        draft_id = self._required(payload, "draft_id")
        draft = self._repository.get_draft(draft_id)
        if draft is None:
            raise ValueError("找不到待确认的世界草案")
        identities = payload.get("native_identities")
        if not isinstance(identities, list):
            raise ValueError("原住民草案格式无效")
        edited_draft = self._apply_native_identity_edits(draft, identities)
        self._repository.replace_draft(edited_draft)
        input_data = self._draft_input(edited_draft)
        world = self._service.confirm_world(
            edited_draft.id,
            request_id=request_id,
            random_seed=input_data["seed"],
            initial_oc=self._oc_from_input(input_data["firstOc"]),
        )
        return self._world_details(world.id)

    def _add_oc(self, payload: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        world_id = self._world_id(payload)
        world = self._repository.require_world(world_id)
        oc = self._oc_from_input(self._oc_input(payload.get("oc")))
        self._service.add_oc(
            world_id,
            oc,
            entry_time=oc.identity["entry_time"],
            expected_revision=world.revision,
            request_id=request_id,
        )
        return self._world_details(world_id)

    def _switch_oc(self, payload: dict[str, Any]) -> dict[str, Any]:
        world_id = self._world_id(payload)
        world = self._repository.require_world(world_id)
        self._service.switch_oc(world_id, self._required(payload, "oc_id"), expected_revision=world.revision)
        return self._world_details(world_id)

    def _submit_action(self, payload: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        world_id = self._world_id(payload)
        content = self._required(payload, "content")
        world = self._repository.require_world(world_id)
        active_oc = self._active_oc(world_id, world.active_oc_id)
        run = self._service.start_run(
            world_id,
            kind="action",
            request_id=f"{request_id}:run",
            expected_revision=world.revision,
            random_seed=f"{world.random_state}:{request_id}",
        )
        proposal = self._proposal(
            world=world,
            run_id=run.id,
            random_seed=run.random_seed,
            event_type="scene.action.committed",
            effective_at=world.current_time,
            participants=(active_oc.id,),
            location=active_oc.location,
            presentation={"kind": "action", "content": content, "speaker_name": active_oc.name},
            projection_patch={"last_action": {"oc": active_oc.id, "content": content}},
        )
        self._service.submit_action(proposal, request_id=request_id)
        return {"run_id": run.id}

    def _advance(self, payload: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        world_id = self._world_id(payload)
        world = self._repository.require_world(world_id)
        active_oc = self._active_oc(world_id, world.active_oc_id)
        run = self._service.start_run(
            world_id,
            kind="advance",
            request_id=f"{request_id}:run",
            expected_revision=world.revision,
            random_seed=f"{world.random_state}:{request_id}",
        )
        next_time = self._next_time(world.current_time)
        proposal = self._proposal(
            world=world,
            run_id=run.id,
            random_seed=run.random_seed,
            event_type="world.time.advanced",
            effective_at=next_time,
            participants=(active_oc.id,),
            location=active_oc.location,
            presentation={"kind": "environment", "content": "时间向前流去，新的机会正在靠近。"},
        )
        self._service.advance(proposal, request_id=request_id)
        return {"run_id": run.id}

    def _resolve_barrier(self, payload: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        world_id = self._world_id(payload)
        world = self._repository.require_world(world_id)
        barrier = self._repository.get_barrier(world_id, self._required(payload, "barrier_id"))
        if barrier is None:
            raise ValueError("待决事件已经不存在")
        choice_id = self._required(payload, "choice_id")
        option = next((item for item in barrier.options if str(item.get("id")) == choice_id), None)
        if option is None:
            raise ValueError("不是这个待决事件的选择")
        run = self._service.start_run(
            world_id,
            kind="barrier_resolution",
            request_id=f"{request_id}:run",
            expected_revision=world.revision,
            random_seed=f"{world.random_state}:{request_id}",
        )
        proposal = self._proposal(
            world=world,
            run_id=run.id,
            random_seed=run.random_seed,
            event_type="decision.resolved",
            effective_at=barrier.effective_at,
            participants=(barrier.oc_id,),
            presentation={"kind": "action", "content": str(option.get("label") or "作出了决定")},
        )
        self._service.resolve_barrier(
            world_id,
            barrier.id,
            proposal,
            request_id=request_id,
            resolution={"choice_id": choice_id, "label": option.get("label", "")},
        )
        return self._world_details(world_id)

    def _timeline(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        world_id = self._world_id(payload)
        perspective = str(payload.get("perspective") or "omniscient")
        oc_id = str(payload.get("oc_id") or "")
        entries = []
        for event in self._repository.list_events(world_id):
            known_to = set(event.visibility.get("known_to", ())) if isinstance(event.visibility, dict) else set()
            if perspective == "known" and oc_id and known_to and oc_id not in known_to:
                continue
            entries.append(self._timeline_entry(event, visibility="known" if known_to else "omniscient"))
        return entries

    def _copy_world(self, payload: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        world = self._service.copy_world(self._world_id(payload), self._required(payload, "anchor_id"), request_id=request_id)
        return self._world_details(world.id)

    def _preview_backfill(self, payload: dict[str, Any]) -> dict[str, Any]:
        world_id = self._world_id(payload)
        anchor_id = self._required(payload, "anchor_id")
        anchor = self._repository.get_event(world_id, anchor_id)
        if anchor is None:
            raise ValueError("找不到入场锚点")
        oc = self._oc_input(payload.get("oc"))
        conflicts = self._backfill_conflicts(world_id, oc["entryTime"])
        return {
            "anchorId": anchor.id,
            "oc": oc,
            "stages": [
                {"title": "过去经历", "summary": "日常经历将作为私有历史补入。", "playable": False},
                {"title": "入场时刻", "summary": "重要转折会在共享世界中成为可玩场景。", "playable": True},
            ],
            "conflicts": conflicts,
            "allowed": not conflicts,
        }

    def _commit_backfill(self, payload: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        world_id = self._world_id(payload)
        preview = payload.get("preview")
        if not isinstance(preview, dict):
            raise ValueError("历史补写预览格式无效")
        anchor_id = self._required(preview, "anchorId")
        if self._repository.get_event(world_id, anchor_id) is None:
            raise ValueError("历史入场锚点已经不存在")
        oc = self._oc_from_input(self._oc_input(preview.get("oc")))
        world = self._repository.require_world(world_id)
        self._service.add_oc(
            world_id,
            oc,
            entry_time=oc.identity["entry_time"],
            expected_revision=world.revision,
            request_id=request_id,
        )
        return self._world_details(world_id)

    def _cancel_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        world_id = self._world_id(payload)
        # A run that already committed is intentionally not rolled back.
        run = next((item for item in self._repository.list_runs(world_id) if item.status not in {"completed", "failed", "cancelled"}), None)
        if run is not None:
            self._service.cancel_run(run.id)
        return self._world_details(world_id)

    def _catch_up(self, payload: dict[str, Any]) -> dict[str, Any]:
        world_id = self._world_id(payload)
        cursor = int(str(payload.get("cursor") or "0").strip() or 0)
        messages = self._repository.list_outbox(world_id, after_sequence=cursor)
        beats = [self._beat(message["payload"].get("event", {}), int(message["sequence"])) for message in messages]
        next_cursor = str(messages[-1]["sequence"] if messages else cursor)
        return {"cursor": next_cursor, "beats": beats, "world": self._world_details(world_id)}

    def _redraw_shot(self, payload: dict[str, Any]) -> dict[str, Any]:
        world_id = self._world_id(payload)
        shot_id = self._required(payload, "shot_id")
        existing = self._shots.get((world_id, shot_id), {"id": shot_id, "prompt": "当前场景", "assets": []})
        shot = {**existing, "status": "developing"}
        self._shots[(world_id, shot_id)] = shot
        return shot

    def _world_details(self, world_id: str) -> dict[str, Any]:
        world = self._repository.require_world(world_id)
        ocs = self._repository.list_ocs(world_id)
        residents = self._repository.list_residents(world_id)
        barriers = self._repository.list_pending_barriers(world_id)
        events = self._repository.list_events(world_id)
        active_oc = next((oc for oc in ocs if oc.id == world.active_oc_id), ocs[0] if ocs else None)
        beats = [self._beat(event.to_dict(), index + 1) for index, event in enumerate(events)]
        return {
            **self._summary(world),
            "ocs": [self._oc_view(oc, active=oc.id == world.active_oc_id) for oc in ocs],
            "scene": {
                "title": f"{world.template_snapshot.get('name', '世界')}的此刻",
                "location": active_oc.location if active_oc else "未知地点",
                "timeLabel": world.current_time,
                "participants": [{"id": oc.id, "name": oc.name, "role": "controlled_oc" if oc.id == world.active_oc_id else "observer"} for oc in ocs],
                "beats": beats,
                "actionPrompt": f"{active_oc.name}准备怎么做？" if active_oc else "先创建一位 OC。",
                "opportunities": [],
                "barriers": [self._barrier_view(item, ocs) for item in barriers],
            },
            "relatedCharacters": [{"id": resident.id, "name": resident.name, "relationship": resident.occupation or "世界原住民", "avatarUrl": resident.visual_identity.get("avatar_path")} for resident in residents],
            "performance": {"active": bool(beats), "label": "观看现场演出", "canCancel": False},
        }

    def _summary(self, world: Any) -> dict[str, Any]:
        environment = world.template_snapshot.get("initial_environment", {})
        return {
            "id": world.id,
            "name": world.template_snapshot.get("name", "未命名世界"),
            "premise": environment.get("premise", ""),
            "currentTimeLabel": world.current_time,
            "activeOcId": world.active_oc_id,
            "status": "barrier" if self._repository.list_pending_barriers(world.id) else "action_required",
        }

    def _proposal(self, *, world: Any, run_id: str, random_seed: str, event_type: str, effective_at: str, participants: tuple[str, ...], location: str = "", presentation: dict[str, Any], projection_patch: dict[str, Any] | None = None) -> BeatProposal:
        return BeatProposal(
            schema_version=1,
            proposal_id=f"proposal-{uuid4().hex}",
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
            events=(ProposedEvent(event_type=event_type, effective_at=effective_at, participants=participants, location=location, changes={"presentation": presentation}, dependencies=DependencySet(write_facts=frozenset({event_type}))),),
            projection_patch=projection_patch or {},
        )

    def _beat(self, event: dict[str, Any], order: int) -> dict[str, Any]:
        changes = event.get("changes", {}) if isinstance(event.get("changes"), dict) else {}
        presentation = changes.get("presentation", {}) if isinstance(changes.get("presentation"), dict) else {}
        event_type = str(event.get("event_type") or "world.event")
        return {"id": str(event.get("id") or f"beat-{order}"), "order": order, "timeLabel": str(event.get("effective_at") or ""), "speakerName": presentation.get("speaker_name"), "kind": presentation.get("kind", "environment"), "content": presentation.get("content", self._event_summary(event_type)), "isCritical": event_type.startswith("decision.")}

    def _timeline_entry(self, event: TimelineEvent, *, visibility: str) -> dict[str, Any]:
        return {"id": event.id, "timeLabel": event.effective_at, "title": self._event_title(event.event_type), "summary": self._beat(event.to_dict(), event.sequence)["content"], "visibility": visibility, "involvedNames": self._participant_names(event.world_id, event.participants), "canCopy": True, "canEnter": True}

    @staticmethod
    def _event_title(event_type: str) -> str:
        return {"world.created": "世界开启", "player_oc.joined": "新的入场", "player_oc.backfilled": "补入过去", "scene.action.committed": "行动", "world.time.advanced": "世界继续流动", "decision.resolved": "做出了决定"}.get(event_type, "世界事件")

    @staticmethod
    def _event_summary(event_type: str) -> str:
        return {"world.created": "世界的既定事实从这一刻开始。", "player_oc.joined": "一位新的 OC 来到世界。", "player_oc.backfilled": "新的经历被安全地补入过去。"}.get(event_type, "世界发生了新的变化。")

    def _native_identity(self, resident: NativeResident, role: Any) -> dict[str, Any]:
        return {"roleId": role.id, "roleName": role.name, "nativeName": resident.name, "identity": resident.occupation, "history": "在世界开始前已经拥有自己的生活。", "relationships": "", "accepted": True}

    def _apply_native_identity_edits(self, draft: WorldDraft, identities: list[Any]) -> WorldDraft:
        edits = {str(item.get("roleId")): item for item in identities if isinstance(item, dict) and bool(item.get("accepted"))}
        if len(edits) != len(draft.residents):
            raise ValueError("请确认所有原住民草案")
        residents = []
        for resident in draft.residents:
            source_role_id = next(snapshot.source_role_id for snapshot in draft.role_snapshots if snapshot.id == resident.snapshot_id)
            edit = edits.get(source_role_id)
            if edit is None:
                raise ValueError("原住民草案与世界不一致")
            residents.append(replace(resident, name=self._required(edit, "nativeName"), occupation=self._required(edit, "identity"), prior_experiences=({"summary": self._required(edit, "history")},)))
        return replace(draft, residents=tuple(residents))

    def _backfill_conflicts(self, world_id: str, entry_time: str) -> list[str]:
        try:
            self._service._validate_backfill(world_id, entry_time, DependencySet(write_facts=frozenset({"oc:private_history"})))
        except HistoricalConflictError:
            return ["这段经历会改变已经结算的公共因果。请从更早的节点创建世界副本。"]
        return []

    def _oc_from_input(self, value: dict[str, str]) -> PlayerOC:
        return PlayerOC(id=f"oc-{uuid4().hex}", name=value["name"], persona={"identity": value["identity"]}, identity={"description": value["identity"], "entry_time": value["entryTime"]}, primary_goal=value["primaryGoal"], location=value["entryLocation"], autonomy=AutonomyPolicy(allow_optional_scenes=True))

    def _oc_view(self, oc: PlayerOC, *, active: bool) -> dict[str, Any]:
        return {"id": oc.id, "name": oc.name, "identity": str(oc.identity.get("description") or ""), "location": oc.location, "primaryGoal": oc.primary_goal, "constraints": list(oc.behavior_constraints), "autonomy": "guided" if oc.autonomy.allow_optional_scenes else "manual", "isActive": active}

    def _barrier_view(self, barrier: DecisionBarrier, ocs: list[PlayerOC]) -> dict[str, Any]:
        return {"id": barrier.id, "title": barrier.reason, "context": barrier.reason, "affectedOcNames": self._participant_names(barrier.world_id, (barrier.oc_id,)), "choices": [{"id": str(item.get("id", "")), "label": str(item.get("label", "")), "consequence": item.get("consequence")} for item in barrier.options]}

    def _participant_names(self, world_id: str, participants: tuple[str, ...]) -> list[str]:
        names = {oc.id: oc.name for oc in self._repository.list_ocs(world_id)}
        names.update({resident.id: resident.name for resident in self._repository.list_residents(world_id)})
        return [names[item] for item in participants if item in names]

    def _active_oc(self, world_id: str, oc_id: str | None) -> PlayerOC:
        oc = next((item for item in self._repository.list_ocs(world_id) if item.id == oc_id), None)
        if oc is None:
            raise ValueError("请先选择一位当前 OC")
        return oc

    def _snapshot_for(self, role: Any) -> RoleTemplateSnapshot:
        return RoleTemplateSnapshot(id=f"snapshot-{uuid4().hex}", source_role_id=role.id, source_version=role.updated_at, persona={"name": role.name, "description": role.description}, system_constraints=(role.system_prompt,), visual_profile={"avatar_path": self._asset_path(role.avatar)}, assets=tuple({"path": path} for path in [role.avatar, *role.illustrations] if path))

    def _asset_path(self, relative_path: str | None) -> str | None:
        return str((self._roles.roles_dir / relative_path).resolve()) if relative_path else None

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
        return {"name": self._required(payload, "name"), "premise": self._required(payload, "premise"), "rules": str(payload.get("rules") or ""), "tone": str(payload.get("tone") or ""), "selectedRoleIds": [str(item) for item in selected if str(item).strip()], "seed": self._required(payload, "seed"), "firstOc": oc}

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
        return {"name": self._required(payload, "name"), "identity": self._required(payload, "identity"), "entryTime": parsed.astimezone(timezone.utc).isoformat(), "entryLocation": self._required(payload, "entryLocation"), "primaryGoal": str(payload.get("primaryGoal") or "")}

    @staticmethod
    def _next_time(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return (parsed + timedelta(hours=1)).astimezone(timezone.utc).isoformat()

    @staticmethod
    def _required(payload: dict[str, Any], field: str) -> str:
        value = str(payload.get(field) or "").strip()
        if not value:
            raise ValueError(f"{field} 不能为空")
        return value

    def _world_id(self, payload: dict[str, Any]) -> str:
        return self._required(payload, "world_id")
