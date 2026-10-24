"""The ``COMMANDS`` registry the host provides and plugin tests reuse."""

import pytest

from shiori_sdk.commands import CommandInput, CommandRegistry


async def _reply(_: CommandInput) -> str:
    return "ok"


def test_a_command_head_finds_its_registration_but_plain_text_does_not():
    registry = CommandRegistry()
    _ = registry.register("undo", _reply)
    assert registry.handler(" /UNDO@ShioriBot 3 ") is _reply
    assert registry.handler("undo") is None


def test_a_taken_or_unmatchable_name_is_refused():
    registry = CommandRegistry()
    _ = registry.register("undo", _reply)
    with pytest.raises(ValueError, match="已被注册"):
        _ = registry.register("undo", _reply)
    with pytest.raises(ValueError, match="不合法"):
        _ = registry.register("Undo", _reply)


def test_a_stale_removal_keeps_the_newer_registration():
    async def newer(_: CommandInput) -> str:
        return "newer"

    registry = CommandRegistry()
    remove_old = registry.register("undo", _reply, description="old")
    remove_old()
    _ = registry.register("undo", newer, description="new")
    remove_old()
    assert registry.handler("/undo") is newer
    assert registry.menu() == [("undo", "new")]
