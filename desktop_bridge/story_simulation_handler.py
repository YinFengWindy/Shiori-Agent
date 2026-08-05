"""Desktop bridge commands for the Story visual-novel bounded context."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.roles import RoleStore

from story_simulation.catalog import StoryCatalog
from story_simulation.director import ProviderStoryDirector, StoryDirector
from story_simulation.errors import StoryNotFoundError
from story_simulation.models import StoryPlayerProfile, StoryVisualType
from story_simulation.repository import StoryRepository, payload_hash
from story_simulation.service import StorySimulationService
from story_simulation.story_time import normalize_story_date, normalize_story_time_band

from .story_image_generator import StoryImageGenerator, prompt_mentions_people

EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]


class StorySimulationHandler:
    """Translate stories.* bridge calls into Story-owned operations and events."""

    def __init__(
        self,
        *,
        workspace: Path,
        role_store: RoleStore,
        director: StoryDirector | None = None,
        provider: Any | None = None,
        model: str = "",
        image_tool: Any | None = None,
    ) -> None:
        self._roles = role_store
        self._catalog = StoryCatalog(workspace)
        self._repositories: dict[str, StoryRepository] = {}
        self._director = director or ProviderStoryDirector(provider=provider, model=model)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._resource_tasks: dict[str, asyncio.Task[None]] = {}
        self._image_generator = StoryImageGenerator(image_tool)
        self._recovery_lock = asyncio.Lock()
        self._recovered = False

    async def aclose(self) -> None:
        """Cancel uncommitted Director tasks and release Story connections."""

        tasks = list(self._tasks.values())
        tasks.extend(self._resource_tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            _ = await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._resource_tasks.clear()
        for repository in self._repositories.values():
            repository.close()
        self._repositories.clear()
        self._catalog.close()

    async def handle(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        request_id: str,
        emit_event: EventEmitter,
    ) -> dict[str, Any] | None:
        """Handle one stories.* method or return None for another domain."""

        if not method.startswith("stories."):
            return None
        await self._recover_persisted_stories(emit_event)
        if method == "stories.list":
            include_archived = bool(payload.get("include_archived", False))
            summaries = self._catalog.list_summaries(include_archived=include_archived)
            return {
                "stories": [
                    {
                        **summary,
                        "current_time_band": self._repository(summary["story_id"]).current_time_band(summary["story_id"]),
                        "current_story_date": self._repository(summary["story_id"]).current_story_date(summary["story_id"]),
                    }
                    for summary in summaries
                ]
            }
        if method == "stories.get":
            return {"story": self._repository(self._story_id(payload)).story_read_model(self._story_id(payload))}
        if method == "stories.cg.list":
            return self._cg_gallery()
        if method == "stories.cg.retry":
            return await self._retry_cg(payload, emit_event=emit_event)
        if method == "stories.cg.regenerate":
            return await self._regenerate_cg(payload, emit_event=emit_event)
        if method == "stories.create":
            return await self._create(payload, request_id=request_id, emit_event=emit_event)
        if method == "stories.input":
            return await self._input(payload, request_id=request_id, emit_event=emit_event)
        if method == "stories.continue":
            return await self._continue(payload, request_id=request_id, emit_event=emit_event)
        raise ValueError(f"unknown Story method: {method}")

    async def _create(
        self, payload: dict[str, Any], *, request_id: str, emit_event: EventEmitter
    ) -> dict[str, Any]:
        creation_id = self._creation_id(payload, request_id)
        request_payload_hash = payload_hash(payload)
        title = self._required(payload, "title")
        background = self._required(payload, "background")
        story_date = normalize_story_date(self._required(payload, "story_date"))
        time_band = normalize_story_time_band(self._required(payload, "time_band"))
        role = self._require_role(self._required(payload, "role_id"))
        profile_payload = payload.get("player_profile")
        if not isinstance(profile_payload, dict):
            raise ValueError("player_profile 必须是对象")
        profile = StoryPlayerProfile(
            display_name=str(profile_payload.get("display_name") or ""),
            appearance=str(profile_payload.get("appearance") or ""),
            identity=str(profile_payload.get("identity") or ""),
        )
        existing_story_id = self._catalog.story_id_for_request(
            creation_id, payload_hash=request_payload_hash
        )
        if existing_story_id is not None:
            return await self._complete_create(
                story_id=existing_story_id,
                creation_id=creation_id,
                title=title,
                background=background,
                role=role,
                profile=profile,
                story_date=story_date,
                time_band=time_band,
                emit_event=emit_event,
                emit_accepted=False,
            )
        story_id = f"story-{uuid4().hex}"
        self._catalog.create_entry(
            story_id=story_id,
            title=title,
            request_id=creation_id,
            payload_hash=request_payload_hash,
        )
        try:
            result = await self._complete_create(
                story_id=story_id,
                creation_id=creation_id,
                title=title,
                background=background,
                time_band=time_band,
                story_date=story_date,
                role=role,
                profile=profile,
                emit_event=emit_event,
                emit_accepted=True,
            )
        except Exception:
            self._discard_incomplete_story(story_id)
            raise
        return {**result, "catalog": self._catalog.require_entry(story_id)}

    async def _complete_create(
        self,
        *,
        story_id: str,
        creation_id: str,
        title: str,
        background: str,
        role: Any,
        profile: StoryPlayerProfile,
        story_date: str,
        time_band: str,
        emit_event: EventEmitter,
        emit_accepted: bool,
    ) -> dict[str, Any]:
        """Complete or resume the durable Story and its opening receipt."""

        entry = self._catalog.require_entry(story_id)
        repository = self._create_repository(story_id)
        service = self._service(repository)
        try:
            story = repository.story_read_model(story_id)
        except StoryNotFoundError:
            if entry["status"] != "provisioning":
                raise
            story = service.create_story(
                story_id=story_id,
                title=title,
                background=background,
                role=role,
                player_profile=profile,
                story_date=story_date,
                time_band=time_band,
                opening_context={"background": background, "role_id": role.id},
            )
        try:
            opening_turn = repository.opening_turn(story_id)
        except StoryNotFoundError:
            opening_turn = service.create_opening_turn(
                story_id=story_id,
                request_id=f"{creation_id}:opening",
            )
        if entry["status"] == "provisioning":
            self._catalog.set_status(story_id, "active")
        if opening_turn["status"] == "pending":
            self._start_generation(service, opening_turn, emit_event)
        if emit_accepted:
            await self._emit(
                emit_event,
                "stories.turn.accepted",
                {
                    "event_type": "turn.accepted",
                    "story_id": story_id,
                    "turn_id": opening_turn["id"],
                    "story_revision": story["revision"],
                },
            )
        return {
            "story": story,
            "turn_id": opening_turn["id"],
            "state": story["segment"],
        }

    async def _recover_persisted_stories(self, emit_event: EventEmitter) -> None:
        """Repair durable Story creation state once after the bridge starts."""

        if self._recovered:
            return
        async with self._recovery_lock:
            if self._recovered:
                return
            for entry in self._catalog.list_entries():
                story_id = str(entry["story_id"])
                try:
                    repository = self._repository(story_id)
                    repository.story_read_model(story_id)
                except StoryNotFoundError:
                    if entry["status"] == "active":
                        self._catalog.set_status(story_id, "deleting")
                    continue
                service = self._service(repository)
                try:
                    opening_turn = repository.opening_turn(story_id)
                except StoryNotFoundError:
                    creation_id = self._catalog.request_id_for_story(story_id)
                    if creation_id is None:
                        continue
                    opening_turn = service.create_opening_turn(
                        story_id=story_id,
                        request_id=f"{creation_id}:opening",
                    )
                if entry["status"] == "provisioning":
                    self._catalog.set_status(story_id, "active")
                if opening_turn["status"] in {"generating", "validating"}:
                    opening_turn = repository.reset_interrupted_turn(opening_turn["id"])
                if opening_turn["status"] == "pending":
                    self._start_generation(service, opening_turn, emit_event)
                if opening_turn["status"] == "committed":
                    await self._fail_interrupted_resources(repository, story_id, emit_event)
            self._recovered = True

    async def _fail_interrupted_resources(
        self,
        repository: StoryRepository,
        story_id: str,
        emit_event: EventEmitter,
    ) -> None:
        """Make resources left generating by a crashed process explicitly retryable."""

        for resource in repository.story_resources(story_id):
            if resource["status"] != "generating":
                continue
            updated = repository.fail_resource(str(resource["id"]), "generation_interrupted")
            await self._emit_resource_changed(repository, updated, emit_event)

    async def _emit_resource_changed(
        self,
        repository: StoryRepository,
        resource: dict[str, Any],
        emit_event: EventEmitter,
    ) -> None:
        """Broadcast the durable visual-resource state to renderer subscribers."""

        story = repository.story_read_model(str(resource["storyId"]))
        await self._emit(
            emit_event,
            "stories.resource.changed",
            {
                "event_type": "resource.changed",
                "story_id": story["id"],
                "story_revision": story["revision"],
                "resource": resource,
            },
        )

    async def _input(
        self, payload: dict[str, Any], *, request_id: str, emit_event: EventEmitter
    ) -> dict[str, Any]:
        story_id = self._story_id(payload)
        service = self._service(self._repository(story_id))
        turn = service.create_player_turn(
            story_id=story_id,
            input_text=self._required(payload, "input"),
            request_id=request_id,
            expected_revision=self._expected_revision(payload),
            request_payload_hash=payload_hash(payload),
        )
        self._start_generation(service, turn, emit_event)
        story = service.repository.story_read_model(story_id)
        await self._emit(
            emit_event,
            "stories.turn.accepted",
            {
                "event_type": "turn.accepted",
                "story_id": story_id,
                "turn_id": turn["id"],
                "story_revision": story["revision"],
            },
        )
        return {"story": story, "turn_id": turn["id"], "state": story["segment"]}

    async def _continue(
        self, payload: dict[str, Any], *, request_id: str, emit_event: EventEmitter
    ) -> dict[str, Any]:
        story_id = self._story_id(payload)
        service = self._service(self._repository(story_id))
        turn = service.create_player_turn(
            story_id=story_id,
            input_text="继续故事。",
            request_id=request_id,
            expected_revision=self._expected_revision(payload),
            request_payload_hash=payload_hash(payload),
            kind="continue",
        )
        self._start_generation(service, turn, emit_event)
        story = service.repository.story_read_model(story_id)
        await self._emit(
            emit_event,
            "stories.turn.accepted",
            {
                "event_type": "turn.accepted",
                "story_id": story_id,
                "turn_id": turn["id"],
                "story_revision": story["revision"],
            },
        )
        return {"story": story, "turn_id": turn["id"], "state": story["segment"]}

    def _cg_gallery(self) -> dict[str, Any]:
        """Return Story-owned CG resources grouped by Story for the main menu."""

        groups: list[dict[str, Any]] = []
        for summary in self._catalog.list_summaries(include_archived=True):
            if summary["status"] == "deleting":
                continue
            story_id = str(summary["story_id"])
            groups.append(
                {
                    "story_id": story_id,
                    "title": summary["title"],
                    "status": summary["status"],
                    "created_at": summary["created_at"],
                    "items": self._repository(story_id).story_resources(story_id),
                }
            )
        return {"stories": groups}

    async def _retry_cg(
        self, payload: dict[str, Any], *, emit_event: EventEmitter
    ) -> dict[str, Any]:
        """Retry one failed resource while keeping the Story transcript unchanged."""

        story_id = self._story_id(payload)
        resource_id = self._required(payload, "resource_id")
        repository = self._repository(story_id)
        resource = repository.resource(resource_id)
        if resource["storyId"] != story_id:
            raise StoryNotFoundError("Story resource 不属于当前 Story")
        if resource["status"] != "failed":
            raise ValueError("资源当前不可重试")
        prepared = repository.prepare_resource(
            resource_id,
            prompt=str(resource.get("prompt") or ""),
            source_turn_id=resource.get("sourceTurnId"),
        )
        await self._emit_resource_changed(repository, prepared, emit_event)
        service = self._service(repository)
        self._start_resource_generation(service, prepared, emit_event)
        return {"story": repository.story_read_model(story_id), "resource_id": resource_id}

    async def _regenerate_cg(
        self, payload: dict[str, Any], *, emit_event: EventEmitter
    ) -> dict[str, Any]:
        """Regenerate a CG in place without adding another gallery resource."""

        story_id = self._story_id(payload)
        resource_id = self._required(payload, "resource_id")
        repository = self._repository(story_id)
        resource = repository.resource(resource_id)
        if resource["storyId"] != story_id:
            raise StoryNotFoundError("Story resource 不属于当前 Story")
        if resource["kind"] != "cg":
            raise ValueError("只有 CG 资源可以重新生成")
        if resource["status"] == "generating":
            raise ValueError("资源正在生成")
        prepared = repository.prepare_resource(
            resource_id,
            prompt=str(resource.get("prompt") or ""),
            source_turn_id=resource.get("sourceTurnId"),
        )
        await self._emit_resource_changed(repository, prepared, emit_event)
        self._start_resource_generation(self._service(repository), prepared, emit_event)
        return {
            "story": repository.story_read_model(story_id),
            "resource_id": resource_id,
        }

    def _schedule_story_cg(
        self,
        story: dict[str, Any],
        turn: dict[str, Any],
        prompt: str,
        visual_type: StoryVisualType,
        emit_event: EventEmitter,
    ) -> None:
        """Schedule one important visual node without delaying committed Story text."""

        story_id = str(story["id"])
        repository = self._repository(story_id)
        if any(
            resource["kind"] == "cg" and resource["status"] == "generating"
            for resource in repository.story_resources(story_id)
        ):
            return
        if visual_type == "scene" and prompt_mentions_people(prompt):
            visual_type = "character"
        resource = repository.create_resource(
            story_id,
            kind="cg",
            prompt=prompt,
            source_turn_id=str(turn["id"]),
            visual_type=visual_type,
        )
        self._start_resource_generation(self._service(repository), resource, emit_event)

    def _start_resource_generation(
        self,
        service: StorySimulationService,
        resource: dict[str, Any],
        emit_event: EventEmitter,
    ) -> None:
        """Run one prepared visual resource and remove its task after completion."""

        resource_id = str(resource["id"])
        existing = self._resource_tasks.get(resource_id)
        if existing is not None and not existing.done():
            return
        task = asyncio.create_task(
            service.generate_resource(resource, emit_event),
            name=f"story-resource:{resource_id}",
        )
        self._resource_tasks[resource_id] = task
        task.add_done_callback(
            lambda _task, resource_id=resource_id: self._resource_tasks.pop(
                resource_id, None
            )
        )

    def _start_generation(
        self, service: StorySimulationService, turn: dict[str, Any], emit_event: EventEmitter
    ) -> None:
        turn_id = str(turn["id"])
        existing = self._tasks.get(turn_id)
        if existing is not None and not existing.done():
            return
        task = asyncio.create_task(
            service.generate_turn(
                turn,
                emit_event,
                schedule_visual_resource=self._schedule_story_cg,
            ),
            name=f"story-director:{turn_id}",
        )
        self._tasks[turn_id] = task
        task.add_done_callback(lambda _task, turn_id=turn_id: self._tasks.pop(turn_id, None))

    def _repository(self, story_id: str) -> StoryRepository:
        repository = self._repositories.get(story_id)
        if repository is not None:
            return repository
        db_path = self._catalog.database_path(story_id)
        if not db_path.exists():
            raise StoryNotFoundError(f"Story database is missing: {story_id}")
        repository = StoryRepository(db_path)
        self._repositories[story_id] = repository
        return repository

    def _create_repository(self, story_id: str) -> StoryRepository:
        """Open the freshly registered private database exactly once."""

        existing = self._repositories.get(story_id)
        if existing is not None:
            return existing
        repository = StoryRepository(self._catalog.database_path(story_id))
        self._repositories[story_id] = repository
        return repository

    def _discard_incomplete_story(self, story_id: str) -> None:
        """Remove a locally-created Story that never reached its opening Turn."""

        repository = self._repositories.pop(story_id, None)
        if repository is not None:
            repository.close()
        try:
            story_path = self._catalog.database_path(story_id).parent
        except StoryNotFoundError:
            return
        self._catalog.delete_entry(story_id)
        if story_path.exists():
            shutil.rmtree(story_path)

    def _service(self, repository: StoryRepository) -> StorySimulationService:
        return StorySimulationService(
            repository=repository,
            director=self._director,
            image_generator=self._image_generator,
        )

    def _require_role(self, role_id: str):
        role = self._roles.get_role(role_id)
        if role is None:
            raise KeyError(f"role not found: {role_id}")
        return role

    @staticmethod
    def _required(payload: dict[str, Any], key: str) -> str:
        value = str(payload.get(key) or "").strip()
        if not value:
            raise ValueError(f"{key} 不能为空")
        return value

    @staticmethod
    def _creation_id(payload: dict[str, Any], request_id: str) -> str:
        """Resolve the stable logical create key or retain transport compatibility."""

        value = str(payload.get("creation_id") or "").strip()
        return value or request_id

    @classmethod
    def _story_id(cls, payload: dict[str, Any]) -> str:
        return cls._required(payload, "story_id")

    @staticmethod
    def _expected_revision(payload: dict[str, Any]) -> int:
        raw = payload.get("expected_revision")
        if isinstance(raw, bool):
            raise ValueError("expected_revision 必须是非负整数")
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("expected_revision 必须是非负整数") from exc
        if value < 0:
            raise ValueError("expected_revision 必须是非负整数")
        return value

    @staticmethod
    async def _emit(
        emit_event: EventEmitter, method: str, payload: dict[str, Any]
    ) -> None:
        result = emit_event(
            {
                "id": f"story-event:{uuid4().hex}",
                "type": "event",
                "method": method,
                "payload": payload,
            }
        )
        if hasattr(result, "__await__"):
            await result
