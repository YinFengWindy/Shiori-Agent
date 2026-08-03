"""Small immutable-shaped data objects shared by Story services."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from .story_time import normalize_story_time_band

StoryResourceKind = Literal["background", "cg"]
StoryResourceStatus = Literal["generating", "ready", "failed"]


def utc_now() -> str:
    """Return an RFC 3339 timestamp used for audit fields."""

    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class StoryPlayerProfile:
    """The player identity frozen into one Story opening context."""

    display_name: str
    appearance: str
    identity: str

    def validate(self) -> None:
        if not self.display_name.strip():
            raise ValueError("player_profile.display_name 不能为空")
        if not self.appearance.strip():
            raise ValueError("player_profile.appearance 不能为空")
        if not self.identity.strip():
            raise ValueError("player_profile.identity 不能为空")

    def to_dict(self) -> dict[str, str]:
        return {
            "display_name": self.display_name,
            "appearance": self.appearance,
            "identity": self.identity,
        }


@dataclass(frozen=True)
class StoryBeatDraft:
    """One candidate visible beat emitted by a Director."""

    text: str
    kind: str = "narration"
    speaker: str | None = None
    time_band: str | None = None
    fact_changes: tuple[dict[str, Any], ...] = ()

    def validate(self) -> None:
        if not self.text.strip():
            raise ValueError("beat.text 不能为空")
        if self.kind not in {"dialogue", "action", "narration"}:
            raise ValueError("beat.kind 无效")
        if len(self.text) > 400:
            raise ValueError("单个 Beat 文本不能超过 400 字符")
        if self.time_band is not None:
            normalize_story_time_band(self.time_band)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "kind": self.kind,
            "speaker": self.speaker,
            "time_band": self.time_band,
            "fact_changes": list(self.fact_changes),
        }


@dataclass(frozen=True)
class DirectorDraft:
    """Validated-shape-independent Director result before Story commit."""

    beats: tuple[StoryBeatDraft, ...]
    stop_reason: str = "awaiting_player"
    visual_prompt: str = ""

    def validate(self) -> None:
        if not self.beats:
            raise ValueError("Director 至少需要一个 Beat")
        if len(self.beats) > 3:
            raise ValueError("一次输入最多生成 3 个 Beat")
        if sum(len(item.text) for item in self.beats) > 1200:
            raise ValueError("一次输入可见文本不能超过 1200 字符")
        for beat in self.beats:
            beat.validate()


@dataclass(frozen=True)
class StoryResource:
    """One Story-owned visual resource and its generation lifecycle."""

    id: str
    story_id: str
    kind: StoryResourceKind
    status: StoryResourceStatus
    path: str | None
    prompt: str
    source_turn_id: str | None
    sequence: int
    error_code: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "storyId": self.story_id,
            "kind": self.kind,
            "status": self.status,
            "path": self.path,
            "prompt": self.prompt,
            "sourceTurnId": self.source_turn_id,
            "sequence": self.sequence,
            "errorCode": self.error_code,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass(frozen=True)
class StoryBeat:
    """A committed Story fact that can be presented."""

    id: str
    story_id: str
    segment_id: str
    turn_id: str
    sequence: int
    time_band: str
    text: str
    kind: str
    speaker: str | None
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "story_id": self.story_id,
            "segment_id": self.segment_id,
            "turn_id": self.turn_id,
            "sequence": self.sequence,
            "time_band": self.time_band,
            "text": self.text,
            "kind": self.kind,
            "speaker": self.speaker,
            "recorded_at": self.recorded_at,
        }


@dataclass(frozen=True)
class PresentationCue:
    """Immutable presentation definition derived from one committed Beat."""

    id: str
    beat_id: str
    story_id: str
    text: str
    kind: str
    speaker: str | None
    tts_status: str = "pending"
    visual_status: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "beat_id": self.beat_id,
            "story_id": self.story_id,
            "text": self.text,
            "kind": self.kind,
            "speaker": self.speaker,
            "tts_status": self.tts_status,
            "visual_status": self.visual_status,
        }


@dataclass(frozen=True)
class StoryContext:
    """Director input assembled from frozen context and committed history."""

    story: dict[str, Any]
    role_snapshot: dict[str, Any]
    player_profile: dict[str, Any]
    segment: dict[str, Any]
    recent_turns: tuple[dict[str, Any], ...] = ()
    recent_beats: tuple[dict[str, Any], ...] = ()
    context_summary: str = ""


@dataclass
class StoryRuntimeState:
    """Mutable service-owned task registry, not a persisted Story fact."""

    tasks: dict[str, Any] = field(default_factory=dict)
