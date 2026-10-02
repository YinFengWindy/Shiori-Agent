"""Session identity fixtures using explicit in-memory metadata."""

from collections.abc import Callable
from .sessions import FakeSessions


class FakeIdentityIndex:
    """Lookup fixture that applies the platform's provided normalization and admission."""

    def __init__(
        self,
        sessions: "FakeChannelSessions",
        channel: str,
        key: str,
        normalizer: Callable[[str], str] | None,
        accepts: Callable[[str], bool] | None,
    ):
        self.sessions, self.channel, self.key = sessions, channel, key
        self.normalize = normalizer or (lambda value: value)
        self.accepts = accepts or (lambda value: True)
        self.mapping: dict[str, str] = {}

    def rebuild(self) -> dict[str, str]:
        """Use only metadata seeded in this fixture."""
        self.mapping.clear()
        for name, session in self.sessions.sessions.items():
            if name.startswith(self.channel + ":"):
                chat_id = name[len(self.channel) + 1 :]
                value = session.metadata.get(self.key)
                if isinstance(value, str) and value.strip() and self.accepts(chat_id):
                    self.mapping[self.normalize(value.strip())] = chat_id
        return dict(self.mapping)

    def resolve(self, identity: str) -> str | None:
        """Resolve a normalized fixture identity."""
        return self.mapping.get(self.normalize(identity.strip()))

    async def remember(self, identity: str, chat_id: str) -> None:
        """Record an accepted identity using the fixture metadata capability."""
        value = self.normalize(identity.strip())
        if value and self.accepts(chat_id):
            self.mapping[value] = chat_id
            await self.sessions.remember_channel_identity(
                self.channel, chat_id, self.key, value
            )


class FakeChannelSessions(FakeSessions):
    """A single metadata fixture shared by all channel identity tests."""

    def identity_index(
        self,
        *,
        channel: str,
        metadata_key: str,
        normalizer: Callable[[str], str] | None = None,
        accepts_chat_id: Callable[[str], bool] | None = None,
    ):
        """Build a fixture view without host persistence."""
        return FakeIdentityIndex(
            self, channel, metadata_key, normalizer, accepts_chat_id
        )

    def get_channel_metadata(self, channel: str) -> list[dict[str, object]]:
        """Return the metadata explicitly seeded for a channel."""
        return [
            {"chat_id": name[len(channel) + 1 :], "metadata": session.metadata}
            for name, session in self.sessions.items()
            if name.startswith(channel + ":")
        ]

    async def remember_channel_identity(
        self, channel: str, chat_id: str, key: str, value: str
    ) -> None:
        """Update the fixture's normalized identity."""
        self.get_or_create(f"{channel}:{chat_id}").metadata[key] = value
