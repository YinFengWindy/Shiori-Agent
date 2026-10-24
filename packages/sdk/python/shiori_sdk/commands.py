"""Bot command turns: what a handler reads, and the ``COMMANDS`` registry.

The host provides a ``CommandRegistry`` as ``COMMANDS``
(``shiori_sdk.core.conversation``) for each plugin generation; plugin tests
provide their own on the fake context's kernel.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shiori_sdk.core.conversation import CommandHandler


@dataclass(frozen=True)
class CommandInput:
    """One command turn: the message and its session's memory progress.

    ``last_consolidated`` is memory progress, independent of model compaction.
    """

    content: str
    session_key: str
    messages: tuple[Mapping[str, object], ...] = ()
    last_consolidated: int = 0


def normalize_command(content: str) -> str:
    """Return the lowercase command head without a bot suffix or arguments."""
    parts = content.strip().split(maxsplit=1)
    return parts[0].lower().split("@", 1)[0] if parts else ""


def command_name(content: str) -> str | None:
    """The name of the bot command ``content`` invokes, or None for no command.

    ``/Undo@bot 3`` names ``undo``; text without a leading slash names none.
    """
    head = normalize_command(content)
    return head[1:] or None if head.startswith("/") else None


@dataclass(frozen=True)
class _Registration:
    handler: CommandHandler
    description: str | None


class CommandRegistry:
    """The ``Commands`` socket: registrations by name, in registration order."""

    def __init__(self) -> None:
        self._commands: dict[str, _Registration] = {}

    def register(
        self, name: str, handler: CommandHandler, *, description: str | None = None
    ) -> Callable[[], None]:
        """See ``Commands.register``; an invalid or taken name raises ``ValueError``."""
        if command_name(f"/{name}") != name:
            raise ValueError(f"命令名不合法: {name!r}")
        if name in self._commands:
            raise ValueError(f"命令 /{name} 已被注册")
        registration = _Registration(handler, description)
        self._commands[name] = registration

        def remove() -> None:
            if self._commands.get(name) is registration:
                del self._commands[name]

        return remove

    def handler(self, content: str) -> CommandHandler | None:
        """The handler of the command ``content`` invokes, None when nobody registered it."""
        name = command_name(content)
        found = None if name is None else self._commands.get(name)
        return None if found is None else found.handler

    def menu(self) -> list[tuple[str, str]]:
        """``(name, description)`` of the described commands, for channel menus."""
        return [
            (name, registration.description)
            for name, registration in self._commands.items()
            if registration.description is not None
        ]
