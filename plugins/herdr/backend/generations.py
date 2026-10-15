"""Generation capabilities for process resources that outlive configuration reloads.

A process resource is built idle and must not retain any generation's
capabilities. Every generation attaches its own instead, and the resource uses
only the published generation's: never a retired one, nor a candidate that has
not been published yet.
"""

from dataclasses import dataclass
from pathlib import Path

from shiori_sdk.process_resources import PluginProcessResources
from shiori_sdk.processes import Processes


class NoPublishedGeneration(RuntimeError):
    """No generation is published: the plugin is between configurations."""

    def __init__(self) -> None:
        super().__init__("Herdr 插件正在切换配置，请稍后重试")


@dataclass(frozen=True)
class _Attachment:
    """One generation's capabilities, usable while that generation is published."""

    resources: PluginProcessResources
    processes: Processes
    directory: Path


class Generations:
    """The capabilities generations attached, read as the published one's."""

    def __init__(self) -> None:
        self._attachments: list[_Attachment] = []

    def attach(
        self, resources: PluginProcessResources, processes: Processes, directory: Path
    ) -> None:
        """A generation offers its capabilities; they are used once it is published.

        Generations no longer published are dropped: a retired one never returns.
        """
        self._attachments = [
            attachment
            for attachment in self._attachments
            if attachment.resources.active
        ]
        self._attachments.append(_Attachment(resources, processes, directory))

    def current(self) -> tuple[Processes, Path] | None:
        """The published generation's process capability and directory, if any."""
        for index in range(len(self._attachments) - 1, -1, -1):
            attachment = self._attachments[index]
            if attachment.resources.active:
                # Older generations were retired by this one and never return.
                del self._attachments[:index]
                return attachment.processes, attachment.directory
        return None

    def clear(self) -> None:
        """Forget every generation; the owning resource is closing."""
        self._attachments.clear()
