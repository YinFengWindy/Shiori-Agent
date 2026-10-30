"""Role lifecycle and committed scene values shared with plugins."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ProactiveMessageCommitted:
    """A proactive role message is available in its shared session.

    ``thread_id`` is the conversation the message belongs to. A role's shared
    session mixes threads, so subscribers read history with this id. A session
    that is not shared across threads passes an empty string.

    ``message_id`` names the committed message, so listeners publish that
    message instead of guessing from the session tail.

    The host publishes this on the domain event bus. The class lives here so a
    plugin subscription and the host publisher share one type.
    """

    session_key: str
    channel: str
    role_id: str
    thread_id: str
    chat_id: str = ""
    assistant_response: str = ""
    tools_used: tuple[str, ...] = ()
    message_id: str = ""


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
