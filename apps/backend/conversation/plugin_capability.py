"""The ``bot_commands`` plugin capability (#901 P2).

``PluginBotCommands`` is the ``host.bot_commands`` core service: each plugin's
command-menu entries, read back for the active plugins in kernel order. The
conversation module's other plugin services live in ``external_turns`` and
``background_results``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.plugin_host.capabilities import ContributionsByPlugin, contribute_to_list
from agent.plugin_host.core_keys import HOST_BOT_COMMANDS, PluginBinding

if TYPE_CHECKING:
    from agent.plugin_host import PluginKernel


class PluginBotCommands(ContributionsByPlugin[tuple[str, str]]):
    """The ``host.bot_commands`` core service of one plugin kernel generation."""

    def for_plugin(self, binding: PluginBinding) -> BotCommandsCapability:
        """The bot commands capability of the plugin ``binding`` describes."""
        return BotCommandsCapability(self.of(binding.plugin_id), binding)


def active_plugin_bot_commands(kernel: PluginKernel) -> list[tuple[str, str]]:
    """The bot commands the generation's active plugins contributed, in kernel order."""
    return kernel.active_contributions(HOST_BOT_COMMANDS)


class BotCommandsCapability:
    """贡献 bot 命令（如 Telegram `/xxx`）；卸载时随 effect 从聚合列表摘除。"""

    def __init__(self, commands: list[tuple[str, str]], binding: PluginBinding) -> None:
        self._commands = commands
        self._effects = binding.scope

    def add(self, command: str, description: str) -> None:
        """Lists ``/command`` with ``description`` until the plugin stops."""
        contribute_to_list(
            self._commands,
            (command, description),
            effects=self._effects,
            label=f"bot_command:{command}",
        )
