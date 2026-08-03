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
from story_simulation.models import StoryPlayerProfile
from story_simulation.repository import StoryRepository, payload_hash
from story_simulation.service import StorySimulationService
from story_simulation.story_time import normalize_story_time_band

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
    ) -> None:
        self._roles = role_store
        self._catalog = StoryCatalog(workspace)
        self._repositories: dict[str, StoryRepository] = {}
        self._director = director or ProviderStoryDirector(provider=provider, model=model)
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def aclose(self) -> None:
        """Cancel uncommitted Director tasks and release Story connections."""

        tasks = list(self._tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            _ = await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
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
        if method == "stories.list":
            include_archived = bool(payload.get("include_archived", False))
            summaries = self._catalog.list_summaries(include_archived=include_archived)
            return {
                "stories": [
                    {
                        **summary,
                        "current_time_band": self._repository(summary["story_id"]).current_time_band(summary["story_id"]),
                    }
                    for summary in summaries
                ]
            }
        if method == "stories.get":
            return {"story": self._repository(self._story_id(payload)).story_read_model(self._story_id(payload))}
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
        request_payload_hash = payload_hash(payload)
        existing_story_id = self._catalog.story_id_for_request(
            request_id, payload_hash=request_payload_hash
        )
        if existing_story_id is not None:
            try:
                repository = self._repository(existing_story_id)
                story = repository.story_read_model(existing_story_id)
                opening_turn = repository.opening_turn(existing_story_id)
            except StoryNotFoundError:
                self._discard_incomplete_story(existing_story_id)
            else:
                return {
                    "story": story,
                    "turn_id": opening_turn["id"],
                    "state": story["segment"],
                }
        title = self._required(payload, "title")
        background = self._required(payload, "background")
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
        story_id = f"story-{uuid4().hex}"
        entry = self._catalog.create_entry(
            story_id=story_id,
            title=title,
            request_id=request_id,
            payload_hash=request_payload_hash,
        )
        try:
            repository = self._create_repository(story_id)
            service = self._service(repository)
            story = service.create_story(
                story_id=story_id,
                title=title,
                background=background,
                role=role,
                player_profile=profile,
                time_band=time_band,
                opening_context={"background": background, "role_id": role.id},
            )
            opening_turn = service.create_opening_turn(
                story_id=story_id,
                request_id=f"{request_id}:opening",
            )
        except Exception:
            self._discard_incomplete_story(story_id)
            raise
        self._start_generation(service, opening_turn, emit_event)
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
            "catalog": entry,
        }

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

    def _start_generation(
        self, service: StorySimulationService, turn: dict[str, Any], emit_event: EventEmitter
    ) -> None:
        turn_id = str(turn["id"])
        existing = self._tasks.get(turn_id)
        if existing is not None and not existing.done():
            return
        task = asyncio.create_task(
            service.generate_turn(turn, emit_event), name=f"story-director:{turn_id}"
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
        return StorySimulationService(repository=repository, director=self._director)

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
