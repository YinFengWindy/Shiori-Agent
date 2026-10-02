"""Session metadata and media replacement fixtures."""

from dataclasses import dataclass, field


@dataclass
class FakeSession:
    """Session metadata sufficient for plugin role resolution."""

    metadata: dict[str, object] = field(default_factory=dict)


class FakeSessions:
    """Controlled session metadata and replace results, with no host persistence."""

    def __init__(self):
        self.sessions: dict[str, FakeSession] = {}
        self.media: dict[tuple[str, str, int], str] = {}
        self.provenance: dict[str, str] = {}
        self.replacement: dict[str, object] = {}

    def get_or_create(self, key: str) -> FakeSession:
        """Return explicitly seeded metadata or an empty fixture."""
        return self.sessions.setdefault(key, FakeSession())

    def role_session_key(self, role_id: str) -> str:
        """Return a stable test session key."""
        return f"role:{role_id}"

    def original_media_path(self, value: str) -> str:
        """Use only fixture-supplied provenance."""
        return self.provenance.get(value, value)

    def get_message_media(
        self, *, session_key: str, message_id: str, media_index: int
    ) -> str:
        """Read one explicitly seeded message slot."""
        return self.media[session_key, message_id, media_index]

    async def replace_message_media(
        self,
        *,
        session_key: str,
        message_id: str,
        media_index: int,
        expected_path: str,
        new_path: str,
    ) -> dict[str, object]:
        """Record the requested replacement and return a supplied host projection."""
        key = (session_key, message_id, media_index)
        if self.media[key] != expected_path:
            raise ValueError("media changed")
        self.media[key] = new_path
        return self.replacement
