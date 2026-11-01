"""Role lifecycle and committed scene values shared with plugins."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RoleDeleted:
    """Signals that role-owned runtime sidecars must discard their state."""

    role_id: str


@dataclass(frozen=True)
class RoleCreated:
    """Signals that a role record and its session now exist.

    Symmetric with ``RoleDeleted``. Plugins may attach role-owned state.
    A failed create does not emit this."""

    role_id: str


@dataclass(frozen=True)
class RoleProactiveChanged:
    """The role's proactive switch changed.

    Temporary until the proactive settings panel owns the switch (P6b PR5).
    Emitted only when ``enabled`` changes, not when the role is created and
    not when a write leaves the switch as it was.
    """

    role_id: str
    enabled: bool


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
