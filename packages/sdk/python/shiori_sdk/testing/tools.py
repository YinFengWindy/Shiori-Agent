"""Tool contribution fixtures."""

from shiori_sdk.tools import Tool


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
