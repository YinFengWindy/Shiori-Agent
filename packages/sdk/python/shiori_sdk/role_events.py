"""Role lifecycle and committed scene values shared with plugins."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RoleDeleted:
    """Signals that role-owned runtime sidecars must discard their state."""

    role_id: str


SceneTransition = Literal["started", "same", "changed", "closed", "none"]
SceneTurnSource = Literal["passive", "proactive"]


@dataclass(frozen=True)
class SceneObservationCommitted:
    """Describes one persistent scene and its current visual beat."""

    session_key: str
    channel: str
    chat_id: str
    role_id: str
    source: SceneTurnSource
    transition: SceneTransition
    scene_key: str = ""
    visual_key: str = ""
    visual_description: str = ""
    role_name: str = ""
    role_description: str = ""
    user_message: str = ""
    assistant_reply: str = ""
    tools_used: tuple[str, ...] = ()
