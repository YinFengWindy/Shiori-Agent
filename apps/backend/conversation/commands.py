"""The ``COMMANDS`` registry of a plugin generation (#902 P3-5).

``bootstrap.plugin_core`` provides each generation's kernel a
``shiori_sdk.commands.CommandRegistry`` as ``COMMANDS``. The before-turn phase
answers the registered commands from it, and the channels started with the
generation list its menu.
"""

from __future__ import annotations

from typing import cast

from shiori_sdk.commands import CommandRegistry
from shiori_sdk.core.conversation import COMMANDS
from shiori_sdk.kernel import Kernel


def generation_commands(kernel: Kernel) -> CommandRegistry | None:
    """``kernel``'s command registry; None on a kernel without plugins.

    Only ``bootstrap.plugin_core`` provides ``COMMANDS`` (a plugin cannot
    provide a core key), so the provider is always a ``CommandRegistry``.
    """
    return cast(CommandRegistry | None, kernel.get(COMMANDS))


def command_menu(kernel: Kernel) -> list[tuple[str, str]]:
    """The ``(name, description)`` menu of ``kernel``'s commands, in registration order."""
    commands = generation_commands(kernel)
    return [] if commands is None else commands.menu()
