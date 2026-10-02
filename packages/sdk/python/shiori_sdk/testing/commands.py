"""Command-phase inputs and explicit session-undo outcomes for independent tests."""

from collections.abc import Callable
from dataclasses import dataclass, field
from shiori_sdk.commands import CommandInput
from shiori_sdk.sessions import UndoSessionResult


@dataclass
class FakeCommandReply:
    """The abort requested by a command contributor."""

    abort_reply: str
    abort: bool = True


@dataclass
class FakeCommandFrame:
    """A phase view with no retrieval, session storage or model execution."""

    command: CommandInput
    slots: dict[str, object] = field(default_factory=dict)

    def abort_command(self, reply: str) -> None:
        """Record the command's request using the normal abort slot."""
        self.slots["session:ctx"] = FakeCommandReply(reply)


class FakeSessionUndo:
    """Return an explicitly seeded host result, recording preview-before-delete order."""

    def __init__(self, result: UndoSessionResult | None = None):
        self.result = result
        self.deleted = False
        self.rollback_sources: list[str] = []
        self.calls: list[str] = []

    async def undo_last_turn(
        self,
        session_key: str,
        *,
        rollback_source_resolver: Callable[[list[str]], list[str]] | None = None,
    ) -> UndoSessionResult | None:
        """Invoke the plugin's resolver before reporting the configured atomic deletion."""
        self.calls.append(session_key)
        if self.result is not None:
            if rollback_source_resolver is not None:
                self.rollback_sources = rollback_source_resolver(
                    list(self.result.deleted_ids)
                )
            self.deleted = True
        return self.result
