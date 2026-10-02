"""SDK-only doubles for tools, resources, HTTP, sessions and opaque key/value state."""

from dataclasses import dataclass, field
from pathlib import Path
from shiori_sdk.tools import Tool
from shiori_sdk.models import ModelToolCall
from shiori_sdk.http import RequestBudget
import httpx


class FakeTools:
    """Record contributions and context without reproducing host execution policy."""

    def __init__(self):
        self.tools: dict[str, Tool] = {}
        self.context: dict[str, str] = {}
        self.options: dict[str, dict[str, object]] = {}

    def register(
        self,
        tool: Tool,
        *,
        risk: str = "read-write",
        always_on: bool = False,
        search_hint: str | None = None,
        external_allowed: bool = False,
    ) -> None:
        """Record one tool and its registration contract."""
        self.tools[tool.name] = tool
        self.options[tool.name] = dict(
            risk=risk,
            always_on=always_on,
            search_hint=search_hint,
            external_allowed=external_allowed,
        )

    def get_tool(self, name: str) -> Tool | None:
        """Look up a registered test tool."""
        return self.tools.get(name)

    def get_context(self) -> dict[str, str]:
        """Read fixture-supplied host context."""
        return dict(self.context)


class FakeKV:
    """Opaque values retained in one test-owned dictionary."""

    def __init__(self):
        self.values: dict[str, object] = {}

    def get(self, key: str, default: object = None) -> object:
        """Read a seeded value."""
        return self.values.get(key, default)

    def set(self, key: str, value: object) -> None:
        """Record a plugin value."""
        self.values[key] = value


class FakeResources:
    """Use explicitly supplied test paths for packaged resources."""

    def __init__(self, root: Path):
        self.root = root

    def common_emojis(self, workspace: Path) -> tuple[Path, ...]:
        """Resolve fixture emoji files without knowing any repository layout."""
        return (workspace / "common_emojis.json", self.root / "common_emojis.json")


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


@dataclass
class FakeModelResponse:
    """Model result used by generation/observation tests without importing a provider."""

    content: str | None
    tool_calls: list[ModelToolCall] = field(default_factory=list)


@dataclass
class FakeToolCall:
    """Explicit tool proposal fixture."""

    id: str
    name: str
    arguments: dict[str, object]


class FakeHttp:
    """Requests must be explicitly replaced by a fixture; never access the network."""

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout_s: float | None = None,
        budget: RequestBudget | None = None,
    ) -> httpx.Response:
        """Fail at the injected transport boundary if a test forgot its response."""
        raise AssertionError(f"Unconfigured HTTP POST: {url}")

    async def get(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        """Fail at the injected transport boundary if a test forgot its response."""
        raise AssertionError(f"Unconfigured HTTP GET: {url}")
