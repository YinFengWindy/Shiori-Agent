"""Tool call events of the core tools module (#902).

``ToolCalling`` runs before a tool executes: ``on`` handlers may rewrite the
arguments or reject the call with ``Veto`` (``ToolVeto`` to also close the
tool loop). It fails closed: a handler error rejects the call. After the
chain the core runs its fixed checks on the final arguments (its minimal
shell guard, and the tool limits of an external-context turn), so no handler
can rewrite a call past them. ``ToolCalled`` follows every call that ran or
was rejected and may rewrite the result. Both are frozen projections of the
host's call: ``arguments`` (and each ``tool_batch`` entry) is frozen into a
read-only mapping on construction, so a handler may build its replacement
with a plain dict, e.g. ``replace(event, arguments={**event.arguments, ...})``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar, Literal, cast

from shiori_sdk.kernel import FailurePolicy, Veto

type ToolSource = Literal["passive", "proactive", "subagent"]
"""Which loop called the tool: a passive turn, proactive work or a subagent."""

type ToolStatus = Literal["success", "denied", "error"]
"""How a call ended: the tool ran, the call was rejected, or the tool raised."""


def _frozen(mapping: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(mapping))


def _frozen_call(call: Mapping[str, object]) -> Mapping[str, object]:
    arguments = call.get("arguments")
    if not isinstance(arguments, Mapping):
        arguments = {}
    return _frozen(
        {**call, "arguments": _frozen(cast(Mapping[str, object], arguments))}
    )


@dataclass(frozen=True)
class ToolCalling:
    """A tool is about to run with ``arguments``.

    ``tool_batch`` holds every call of the same model response as
    ``{"name", "arguments"}`` mappings and ``tool_batch_index`` this call's
    position in it. A passive turn also emits it for a call to a tool not
    loaded yet (still behind ``tool_search``): the tool never runs, only a
    finalizing ``ToolVeto`` takes effect there, and no ``ToolCalled`` follows.

    Writable: ``arguments``.
    """

    on_error: ClassVar[FailurePolicy] = "fail_closed"

    session_key: str
    channel: str
    chat_id: str
    source: ToolSource
    call_id: str
    tool_name: str
    arguments: Mapping[str, object]
    tool_batch: tuple[Mapping[str, object], ...] = ()
    tool_batch_index: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _frozen(self.arguments))
        batch = tuple(_frozen_call(call) for call in self.tool_batch)
        object.__setattr__(self, "tool_batch", batch)


@dataclass(frozen=True)
class ToolVeto(Veto):
    """Rejects a tool call with ``reason`` as its result.

    ``finalize`` also skips the rest of the batch and closes the turn with a
    summary instead of another model step.
    """

    finalize: bool = False


@dataclass(frozen=True)
class ToolCalled:
    """A tool call ended with ``status``; ``arguments`` are the final ones.

    ``result`` is the tool's output as text (the text part of a structured
    ``ToolResult``), or the rejection or error text. It cannot be vetoed: a
    veto fails the loop that made the call.

    Writable: ``result``. Only a changed ``result`` reaches the model, and then
    as plain text: rewriting the result of a tool that returned a structured
    or media ``ToolResult`` replaces it whole, dropping its media and
    structured content. Left unchanged, the tool's own result passes as it is.
    """

    session_key: str
    channel: str
    chat_id: str
    source: ToolSource
    call_id: str
    tool_name: str
    arguments: Mapping[str, object]
    status: ToolStatus
    result: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _frozen(self.arguments))
