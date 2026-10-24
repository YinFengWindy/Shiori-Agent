"""The ``COMMANDS`` registry of a plugin generation (#902 P3-5).

``bootstrap.plugin_core`` provides each generation's kernel a
``shiori_sdk.commands.CommandRegistry`` as ``COMMANDS``. The before-turn phase
answers the registered commands from it, and the channels started with the
generation list its menu.
"""

from __future__ import annotations

from shiori_sdk.commands import CommandRegistry
from shiori_sdk.core.conversation import COMMANDS
from shiori_sdk.kernel import Kernel


def generation_commands(kernel: Kernel) -> CommandRegistry | None:
    """``kernel``'s command registry; None on a kernel without plugins."""
    commands = kernel.get(COMMANDS)
    if commands is None or isinstance(commands, CommandRegistry):
        return commands
    raise TypeError(f"COMMANDS 的提供方不是核心注册表: {type(commands).__name__}")


def command_menu(kernel: Kernel) -> list[tuple[str, str]]:
    """The ``(name, description)`` menu of ``kernel``'s commands, in registration order."""
    commands = generation_commands(kernel)
    return [] if commands is None else commands.menu()
