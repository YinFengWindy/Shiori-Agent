from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from agent.core.types import ToolCallGroup


def _empty_media() -> list[str]:
    return []


def _empty_metadata() -> dict[str, Any]:
    return {}


def _empty_int_metadata() -> dict[str, int]:
    return {}


def _empty_skill_names() -> list[str]:
    return []


def _empty_tool_chain() -> list[dict[str, Any]]:
    return []


def _empty_tool_call_groups() -> list["ToolCallGroup"]:
    return []


@dataclass(frozen=True)
class TurnStarted:
    session_key: str
    channel: str
    chat_id: str
    content: str
    timestamp: datetime
    role_id: str = ""


@dataclass(frozen=True)
class StreamDeltaReady:
    session_key: str
    channel: str
    chat_id: str
    content_delta: str = ""
    thinking_delta: str = ""
    role_id: str = ""


@dataclass
class BeforeReasoning:
    session_key: str
    channel: str
    chat_id: str
    content: str
    skill_names: list[str] = field(default_factory=_empty_skill_names)
    retrieved_memory_block: str = ""
    role_id: str = ""


@dataclass(frozen=True)
class TurnCommitted:
    session_key: str
    channel: str
    chat_id: str
    input_message: str
    persisted_user_message: str | None
    assistant_response: str
    tools_used: list[str]
    thinking: str | None = None
    raw_reply: str | None = None
    meme_tag: str | None = None
    meme_media_count: int | None = None
    tool_chain_raw: list[dict[str, Any]] = field(default_factory=_empty_tool_chain)
    tool_call_groups: list["ToolCallGroup"] = field(
        default_factory=_empty_tool_call_groups
    )
    timestamp: datetime | None = None
    post_reply_budget: dict[str, int] = field(default_factory=_empty_int_metadata)
    react_stats: dict[str, int] = field(default_factory=_empty_int_metadata)
    extra: dict[str, Any] = field(default_factory=_empty_metadata)
    role_id: str = ""
    request_id: str = ""
    thread_id: str = ""


@dataclass(frozen=True)
class ProactiveMessageCommitted:
    """Signals that a proactive role message is available in its shared session."""

    session_key: str
    channel: str
    role_id: str
    chat_id: str = ""
    assistant_response: str = ""
    tools_used: tuple[str, ...] = ()


SceneTransition = Literal["started", "same", "changed", "closed"]
SceneTurnSource = Literal["passive", "proactive"]


@dataclass(frozen=True)
class SceneObservationCommitted:
    """Describes the visual scene inferred from one completed role turn."""

    session_key: str
    channel: str
    chat_id: str
    role_id: str
    source: SceneTurnSource
    transition: SceneTransition
    scene_key: str = ""
    should_generate: bool = False
    prompt: str = ""
    negative_prompt: str = ""
    size_preset: str = "landscape"
    tools_used: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExternalImagePushed:
    """Describes one image successfully delivered through an external channel."""

    session_key: str
    role_id: str
    channel: str
    chat_id: str
    image: str
    attach_to_turn: bool = False
    already_persisted: bool = False


@dataclass(frozen=True)
class ToolCallStarted:
    session_key: str
    channel: str
    chat_id: str
    iteration: int
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    role_id: str = ""


@dataclass(frozen=True)
class ToolCallCompleted:
    session_key: str
    channel: str
    chat_id: str
    iteration: int
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    final_arguments: dict[str, Any]
    status: str
    result_preview: str
    role_id: str = ""
