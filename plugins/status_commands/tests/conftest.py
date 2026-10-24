"""Commands registered on a real ``CommandRegistry``, answered like the host does."""

from dataclasses import dataclass, field

import pytest

from plugins.status_commands.backend import plugin as backend_plugin
from plugins.status_commands.backend.plugin import setup
from shiori_sdk.commands import CommandInput, CommandRegistry
from shiori_sdk.core.conversation import COMMANDS
from shiori_sdk.kernel import Kernel
from shiori_sdk.testing.extensions import FakeDependencies, FakeExtensionContext


@dataclass
class Session:
    key: str = "telegram:1"
    last_consolidated: int = 0
    messages: list[dict[str, object]] = field(default_factory=list)


@dataclass
class Plugin:
    """The plugin set up over ``commands``, with its mutable observe exports."""

    ctx: FakeExtensionContext
    commands: CommandRegistry
    exports: dict[str, object]

    async def answer(self, content: str, session: Session | None = None) -> str | None:
        """The plugin's reply to ``content``, or None when it registered no such command."""
        session = session or Session()
        handler = self.commands.handler(content)
        if handler is None:
            return None
        return await handler(
            CommandInput(
                content, session.key, tuple(session.messages), session.last_consolidated
            )
        )


@pytest.fixture
def backend():
    return backend_plugin


@pytest.fixture
async def plugin():
    kernel, commands = Kernel(), CommandRegistry()
    kernel.provide(COMMANDS, commands)
    exports: dict[str, object] = {}
    ctx = FakeExtensionContext(
        "status_commands",
        dependencies=FakeDependencies(exports),
        kernel=kernel,
        inject=("commands",),
    )
    await setup(ctx)
    yield Plugin(ctx, commands, exports)
    await ctx.aclose()
