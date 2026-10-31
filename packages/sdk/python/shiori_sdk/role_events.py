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
    Creating a role does not emit ``RoleProactiveChanged``: the switch has
    no previous value.
    """

    role_id: str


@dataclass(frozen=True)
class RoleProactiveChanged:
    """The host stored a new value of a role's proactive switch.

    Temporary. The host still writes ``proactive.enabled``. After P6b step 5
    moves that switch fully off the host, delete this event with the write.
    Do not build new behavior on it.

    ``enabled`` is the value just stored. A write that leaves it unchanged
    does not emit this, and creating a role does not either.
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
