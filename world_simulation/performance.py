"""Versioned presentation plans derived from committed world facts."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from collections.abc import Mapping
from typing import Any, Literal

from world_simulation.timeline import TimelineEvent

PRESENTATION_PROTOCOL_VERSION = 1
CueKind = Literal["dialogue", "sprites", "background", "camera", "audio", "cg", "text"]
_CUE_KINDS = frozenset(
    ("dialogue", "sprites", "background", "camera", "audio", "cg", "text")
)


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def plan_id_for_event(
    world_id: str,
    event_id: str,
    *,
    protocol_version: int = PRESENTATION_PROTOCOL_VERSION,
) -> str:
    """Return the stable presentation-plan id for one committed event."""

    if not world_id.strip() or not event_id.strip():
        raise ValueError("world_id and event_id are required")
    return _stable_id("plan", f"{protocol_version}:{world_id}:{event_id}")


def cue_id_for_plan(plan_id: str, sequence: int, kind: CueKind) -> str:
    """Return the stable cue id within one presentation plan."""

    if sequence < 0:
        raise ValueError("cue sequence must be non-negative")
    return _stable_id("cue", f"{plan_id}:{sequence}:{kind}")


@dataclass(frozen=True)
class PresentationCue:
    """One versioned, renderer-facing presentation instruction."""

    schema_version: int
    cue_id: str
    plan_id: str
    sequence: int
    kind: CueKind
    payload: dict[str, Any]
    parallel_group: str | None = None
    blocking: bool = True
    completion_state: str = "completed"
    skip_state: str = "skipped"
    checkpoint: bool = False

    def __post_init__(self) -> None:
        """Reject malformed cues before they cross the bridge boundary."""

        if self.schema_version != PRESENTATION_PROTOCOL_VERSION:
            raise ValueError(f"unsupported presentation schema: {self.schema_version}")
        if not self.cue_id.strip() or not self.plan_id.strip():
            raise ValueError("cue_id and plan_id are required")
        if self.sequence < 0:
            raise ValueError("cue sequence must be non-negative")
        if self.kind not in _CUE_KINDS:
            raise ValueError(f"unsupported cue kind: {self.kind}")
        if self.parallel_group is not None and not self.parallel_group.strip():
            raise ValueError("parallel_group cannot be empty")
        if not self.completion_state.strip() or not self.skip_state.strip():
            raise ValueError("cue terminal states are required")
        if self.completion_state == self.skip_state:
            raise ValueError("cue terminal states must differ")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the internal snake_case protocol envelope."""

        return asdict(self)

    def to_bridge_dict(self) -> dict[str, Any]:
        """Serialize the camelCase envelope exposed to the renderer."""

        return {
            "schemaVersion": self.schema_version,
            "cueId": self.cue_id,
            "planId": self.plan_id,
            "sequence": self.sequence,
            "kind": self.kind,
            "payload": dict(self.payload),
            "parallelGroup": self.parallel_group,
            "blocking": self.blocking,
            "completionState": self.completion_state,
            "skipState": self.skip_state,
            "checkpoint": self.checkpoint,
        }


@dataclass(frozen=True)
class PerformancePlan:
    """Presentation-only instructions that cannot alter world facts."""

    id: str
    world_id: str
    event_id: str
    source_sequence: int = 0
    schema_version: int = PRESENTATION_PROTOCOL_VERSION
    cues: tuple[PresentationCue, ...] = ()
    dialogue: dict[str, Any] | None = None
    sprites: tuple[dict[str, Any], ...] = ()
    background: dict[str, Any] | None = None
    camera: tuple[dict[str, Any], ...] = ()
    audio: tuple[dict[str, Any], ...] = ()
    cg_tasks: tuple[dict[str, Any], ...] = ()
    fallback_text: str = ""

    def validate(self) -> None:
        """Validate plan identity and contiguous cue ordering."""

        if self.schema_version != PRESENTATION_PROTOCOL_VERSION:
            raise ValueError(f"unsupported presentation schema: {self.schema_version}")
        if (
            not self.id.strip()
            or not self.world_id.strip()
            or not self.event_id.strip()
        ):
            raise ValueError("plan identity fields are required")
        if self.source_sequence < 0:
            raise ValueError("source_sequence must be non-negative")
        sequences = [cue.sequence for cue in self.cues]
        if sequences != list(range(len(self.cues))):
            raise ValueError("cue sequences must be contiguous and zero-based")
        if any(cue.plan_id != self.id for cue in self.cues):
            raise ValueError("cue plan_id does not match its parent plan")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the internal snake_case protocol envelope."""

        value = asdict(self)
        value["cues"] = [cue.to_dict() for cue in self.cues]
        return value

    def to_bridge_dict(self) -> dict[str, Any]:
        """Serialize the plan and cues for the renderer bridge."""

        self.validate()
        return {
            "schemaVersion": self.schema_version,
            "planId": self.id,
            "worldId": self.world_id,
            "eventId": self.event_id,
            "sourceSequence": self.source_sequence,
            "cues": [cue.to_bridge_dict() for cue in self.cues],
        }


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_mapping_tuple(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def presentation_mode_for_event(
    event: TimelineEvent | Mapping[str, Any],
) -> Literal["narrative", "scene"]:
    """Classify a committed event without turning ordinary prose into a scene."""

    value = event.to_dict() if isinstance(event, TimelineEvent) else dict(event)
    changes = _as_mapping(value.get("changes"))
    presentation = _as_mapping(changes.get("presentation"))
    explicit = str(presentation.get("mode") or "").strip()
    if explicit == "scene":
        return "scene"
    if explicit == "narrative":
        return "narrative"
    staged_fields = ("dialogue", "sprites", "background", "camera", "audio", "cg_tasks")
    return (
        "scene"
        if any(presentation.get(field) for field in staged_fields)
        else "narrative"
    )


def _cue(
    *,
    plan_id: str,
    sequence: int,
    kind: CueKind,
    payload: dict[str, Any],
    blocking: bool,
    parallel_group: str | None,
) -> PresentationCue:
    return PresentationCue(
        schema_version=PRESENTATION_PROTOCOL_VERSION,
        cue_id=cue_id_for_plan(plan_id, sequence, kind),
        plan_id=plan_id,
        sequence=sequence,
        kind=kind,
        payload=payload,
        parallel_group=parallel_group,
        blocking=blocking,
        checkpoint=blocking,
    )


def compile_performance_plan(
    event: TimelineEvent | Mapping[str, Any],
) -> PerformancePlan:
    """Compile one committed event into a deterministic presentation plan."""

    value = event.to_dict() if isinstance(event, TimelineEvent) else dict(event)
    world_id = str(value.get("world_id") or "")
    event_id = str(value.get("id") or "")
    if not world_id or not event_id:
        raise ValueError("committed event requires world_id and id")
    plan_id = plan_id_for_event(world_id, event_id)
    changes = _as_mapping(value.get("changes"))
    presentation = _as_mapping(changes.get("presentation"))
    event_type = str(value.get("event_type") or "world.event")
    fallback_text = str(
        presentation.get("fallback_text") or presentation.get("content") or event_type
    )
    dialogue_value = _as_mapping(presentation.get("dialogue"))
    if not dialogue_value and presentation.get("content"):
        dialogue_value = {
            "content": str(presentation["content"]),
            "speaker_name": str(presentation.get("speaker_name") or ""),
        }
    sprites = _as_mapping_tuple(presentation.get("sprites"))
    camera = _as_mapping_tuple(presentation.get("camera"))
    audio = _as_mapping_tuple(presentation.get("audio"))
    cg_tasks = _as_mapping_tuple(presentation.get("cg_tasks"))
    background = _as_mapping(presentation.get("background"))
    stage_group = f"stage-{event_id}"
    specs: list[tuple[CueKind, dict[str, Any], bool, str | None]] = []
    if background:
        specs.append(("background", dict(background), False, stage_group))
    if sprites:
        specs.append(("sprites", {"items": list(sprites)}, False, stage_group))
    if camera:
        specs.append(("camera", {"items": list(camera)}, False, stage_group))
    if cg_tasks:
        specs.append(("cg", {"tasks": list(cg_tasks)}, False, stage_group))
    if dialogue_value:
        specs.append(("dialogue", dict(dialogue_value), True, None))
    if audio:
        specs.append(("audio", {"items": list(audio)}, False, stage_group))
    if not specs:
        specs.append(("text", {"text": fallback_text}, True, None))
    cues = tuple(
        _cue(
            plan_id=plan_id,
            sequence=sequence,
            kind=kind,
            payload=payload,
            blocking=blocking,
            parallel_group=parallel_group,
        )
        for sequence, (kind, payload, blocking, parallel_group) in enumerate(specs)
    )
    plan = PerformancePlan(
        id=plan_id,
        world_id=world_id,
        event_id=event_id,
        source_sequence=int(value.get("sequence") or 0),
        schema_version=PRESENTATION_PROTOCOL_VERSION,
        cues=cues,
        dialogue=dict(dialogue_value) if dialogue_value else None,
        sprites=sprites,
        background=dict(background) if background else None,
        camera=camera,
        audio=audio,
        cg_tasks=cg_tasks,
        fallback_text=fallback_text,
    )
    plan.validate()
    return plan
