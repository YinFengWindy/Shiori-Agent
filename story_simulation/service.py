"""Story application service that coordinates Director drafts and commits."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import uuid4

from core.roles.models import RoleRecord

from .continuity import ContinuityGuard
from .director import StoryDirector
from .errors import StoryInvalidOutputError, StorySimulationError
from .models import StoryPlayerProfile, StoryVisualType
from .repository import StoryRepository, payload_hash

EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]
VisualResourceScheduler = Callable[
    [dict[str, Any], dict[str, Any], str, StoryVisualType, EventEmitter], None
]


class StoryImageGenerator(Protocol):
    """Generate one Story-owned image through the configured image boundary."""

    async def generate(
        self, *, story: dict[str, Any], resource: dict[str, Any]
    ) -> str:
        """Return the absolute path of the first generated image."""


class StorySimulationService:
    """Commit Story facts only after a Director draft passes the guard."""

    def __init__(
        self,
        *,
        repository: StoryRepository,
        director: StoryDirector,
        continuity_guard: ContinuityGuard | None = None,
        image_generator: StoryImageGenerator | None = None,
    ) -> None:
        self.repository = repository
        self._director = director
        self._continuity_guard = continuity_guard or ContinuityGuard()
        self._image_generator = image_generator

    def create_story(
        self,
        *,
        story_id: str,
        title: str,
        background: str,
        role: RoleRecord,
        player_profile: StoryPlayerProfile,
        story_date: str,
        time_band: str,
        opening_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Freeze the selected role and create the initial Story segment."""

        return self.repository.create_story(
            story_id=story_id,
            title=title,
            background=background,
            role_snapshot=role.to_dict(),
            player_profile=player_profile,
            story_date=story_date,
            time_band=time_band,
            opening_context=opening_context,
        )

    def create_opening_turn(
        self, *, story_id: str, request_id: str
    ) -> dict[str, Any]:
        """Persist the non-player opening Turn before generation starts."""

        story = self.repository.story_read_model(story_id)
        return self.repository.create_turn(
            story_id=story_id,
            input_text="",
            request_id=request_id,
            expected_revision=int(story["revision"]),
            request_payload_hash=payload_hash(
                {"story_id": story_id, "kind": "opening", "request_id": request_id}
            ),
            kind="opening",
        )

    def create_player_turn(
        self,
        *,
        story_id: str,
        input_text: str,
        request_id: str,
        expected_revision: int,
        request_payload_hash: str,
        kind: str = "player",
    ) -> dict[str, Any]:
        """Persist one player/continue Turn before generation starts."""

        return self.repository.create_turn(
            story_id=story_id,
            input_text=input_text,
            request_id=request_id,
            expected_revision=expected_revision,
            request_payload_hash=request_payload_hash,
            kind=kind,
        )

    async def generate_turn(
        self,
        turn: dict[str, Any],
        emit_event: EventEmitter,
        schedule_visual_resource: VisualResourceScheduler | None = None,
    ) -> None:
        """Run the bounded Director attempt and emit only committed Beat events."""

        turn_id = str(turn["id"])
        opening = turn["kind"] == "opening"
        attempt = self.repository.start_attempt(turn_id)
        attempt_id = str(attempt["attempt_id"])
        for attempt_index in range(2):
            try:
                context = self.repository.build_context(
                    self.repository.story_id_for_turn(turn_id)
                )
                draft = await asyncio.wait_for(
                    self._director.generate(
                        context=context,
                        input_text=str(turn["input"]),
                        opening=opening,
                    ),
                    timeout=30,
                )
                self.repository.mark_validating(turn_id, attempt_id)
                self._continuity_guard.validate(draft, context)
                committed, story = self.repository.commit_draft(
                    turn_id=turn_id,
                    attempt_id=attempt_id,
                    draft=draft,
                    default_time_band=context.segment["timeBand"],
                )
                for _, _, payload in committed:
                    await self._emit(emit_event, "stories.beat.committed", payload)
                if opening:
                    await self._generate_opening_background(
                        story=story,
                        turn_id=turn_id,
                        visual_prompt=draft.visual_prompt,
                        emit_event=emit_event,
                    )
                elif schedule_visual_resource and draft.visual_prompt.strip():
                    schedule_visual_resource(
                        story,
                        turn,
                        draft.visual_prompt,
                        draft.visual_type,
                        emit_event,
                    )
                await self._emit(
                    emit_event,
                    "stories.operation.changed",
                    {
                        "event_type": "operation.changed",
                        "story_id": story["id"],
                        "story_revision": story["revision"],
                        "state": story["segment"],
                        "turn_id": turn_id,
                    },
                )
                return
            except asyncio.CancelledError:
                try:
                    self.repository.cancel_turn(turn_id, attempt_id)
                except StorySimulationError:
                    # The draft may have committed immediately before shutdown.
                    pass
                if opening:
                    await self._fail_opening_background(
                        self.repository.story_id_for_turn(turn_id),
                        "generation_cancelled",
                        emit_event,
                    )
                return
            except Exception as exc:
                code = self._failure_code(exc)
                if attempt_index == 0 and self._is_retryable(exc):
                    replacement = self.repository.retry_attempt(
                        turn_id, attempt_id, failure_category=code
                    )
                    attempt_id = str(replacement["attempt_id"])
                    continue
                story = self.repository.fail_turn(
                    turn_id,
                    attempt_id,
                    code=code,
                    message=str(exc),
                )
                await self._emit(
                    emit_event,
                    "stories.failed",
                    {
                        "event_type": "story.failed",
                        "story_id": story["id"],
                        "story_revision": story["revision"],
                        "turn_id": turn_id,
                        "attempt_id": attempt_id,
                        "code": code,
                        "retryable": False,
                        "message": "剧情生成暂时失败，可以手动重试。",
                    },
                )
                if opening:
                    await self._fail_opening_background(story["id"], code, emit_event)
                return

    async def retry_resource(
        self, resource_id: str, emit_event: EventEmitter
    ) -> dict[str, Any]:
        """Retry one failed Story image without creating another narrative Turn."""

        resource = self.repository.resource(resource_id)
        if resource["status"] != "failed":
            raise StorySimulationError("资源当前不可重试")
        prepared = self.repository.prepare_resource(
            resource_id,
            prompt=str(resource.get("prompt") or ""),
            source_turn_id=resource.get("sourceTurnId"),
        )
        return await self.generate_resource(prepared, emit_event)

    async def generate_resource(
        self, resource: dict[str, Any], emit_event: EventEmitter
    ) -> dict[str, Any]:
        """Run a prepared Story resource request and publish its final state."""

        return await self._generate_resource(resource, emit_event)

    async def _generate_opening_background(
        self,
        *,
        story: dict[str, Any],
        turn_id: str,
        visual_prompt: str,
        emit_event: EventEmitter,
    ) -> None:
        """Generate the Story-owned background attached to the opening Turn."""

        resources = self.repository.story_resources(str(story["id"]))
        background = next(
            (resource for resource in resources if resource["kind"] == "background"),
            None,
        )
        if background is None:
            return
        prepared = self.repository.prepare_resource(
            str(background["id"]),
            prompt=visual_prompt,
            source_turn_id=turn_id,
        )
        await self._generate_resource(prepared, emit_event)

    async def _fail_opening_background(
        self, story_id: str, error_code: str, emit_event: EventEmitter
    ) -> None:
        """Mark the pending opening background failed when the opening Turn stops."""

        resources = self.repository.story_resources(story_id)
        background = next(
            (
                resource
                for resource in resources
                if resource["kind"] == "background"
                and resource["status"] == "generating"
            ),
            None,
        )
        if background is None:
            return
        updated = self.repository.fail_resource(str(background["id"]), error_code)
        await self._emit_resource_changed(emit_event, updated)

    async def _generate_resource(
        self, resource: dict[str, Any], emit_event: EventEmitter
    ) -> dict[str, Any]:
        resource_id = str(resource["id"])
        try:
            if self._image_generator is None:
                raise StorySimulationError("Story 图片生成工具未注册")
            path = await self._image_generator.generate(
                story=self.repository.story_read_model(str(resource["storyId"])),
                resource=resource,
            )
            updated = self.repository.complete_resource(resource_id, path)
        except asyncio.CancelledError:
            updated = self.repository.fail_resource(resource_id, "generation_cancelled")
            await self._emit_resource_changed(emit_event, updated)
            raise
        except Exception as exc:
            updated = self.repository.fail_resource(
                resource_id, self._resource_failure_code(exc)
            )
        await self._emit_resource_changed(emit_event, updated)
        return updated

    async def _emit_resource_changed(
        self, emit_event: EventEmitter, resource: dict[str, Any]
    ) -> None:
        story = self.repository.story_read_model(str(resource["storyId"]))
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

    @staticmethod
    def _resource_failure_code(error: Exception) -> str:
        if isinstance(error, asyncio.TimeoutError):
            return "generation_timeout"
        if isinstance(error, StorySimulationError):
            return error.code
        if isinstance(error, ValueError):
            return "invalid_image_request"
        return "resource_generation_failed"

    @staticmethod
    def _failure_code(error: Exception) -> str:
        if isinstance(error, asyncio.TimeoutError):
            return "generation_timeout"
        if isinstance(error, StorySimulationError):
            return error.code
        return "provider_unavailable"

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        return isinstance(error, (asyncio.TimeoutError, StoryInvalidOutputError)) or not isinstance(
            error, StorySimulationError
        )

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
