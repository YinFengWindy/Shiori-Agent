"""SDK-only command frames and independently owned session observations."""

from dataclasses import dataclass, field
import pytest
from plugins.status_commands.backend import plugin
from shiori_sdk.commands import CommandInput
from shiori_sdk.testing.commands import FakeCommandFrame


@dataclass
class Session:
    key: str = "telegram:1"
    last_consolidated: int = 0
    messages: list[dict[str, object]] = field(default_factory=list)


@pytest.fixture
def backend():
    return plugin


@pytest.fixture
def command_frame():
    def make(content: str, session: Session | None = None):
        session = session or Session()
        return FakeCommandFrame(
            CommandInput(
                content, session.key, tuple(session.messages), session.last_consolidated
            )
        )

    return make
