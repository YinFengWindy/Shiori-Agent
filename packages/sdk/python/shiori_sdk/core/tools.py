"""Tool call events of the core tools module (#902).

``ToolCalling`` runs before a tool executes: ``on`` handlers may rewrite the
arguments or reject the call with ``Veto`` (``ToolVeto`` to also close the
tool loop). It fails closed: a handler error rejects the call. After the
chain the core runs its fixed checks on the final arguments, so no handler
can rewrite a call past them. ``ToolCalled`` follows every call, including a
rejected one, and may rewrite the result. Both are frozen projections of the
host's call; container fields are tuples or read-only mappings.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar, Literal

from shiori_sdk.kernel import FailurePolicy, Veto

type ToolSource = Literal["passive", "proactive", "subagent"]
"""Which loop called the tool: a passive turn, proactive work or a subagent."""

type ToolStatus = Literal["success", "denied", "error"]
"""How a call ended: the tool ran, the call was rejected, or the tool raised."""


@dataclass(frozen=True)
class ToolCalling:
    """A tool is about to run with ``arguments``.

    ``request_text`` is the user message the call serves, when the host knows
    it. ``tool_batch`` holds every call of the same model response as
    ``{"name", "arguments"}`` mappings and ``tool_batch_index`` this call's
    position in it.

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
    request_text: str = ""
    tool_batch: tuple[Mapping[str, object], ...] = ()
    tool_batch_index: int = 0


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

    ``result`` is the tool's output as text, or the rejection or error text.

    Writable: ``result``.
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
