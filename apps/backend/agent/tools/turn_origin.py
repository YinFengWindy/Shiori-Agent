"""Host-only inbound origin snapshot for tools that return asynchronous results."""

from contextvars import ContextVar
from copy import deepcopy
from dataclasses import replace

from shiori_sdk.messages import InboundMessage

_origin: ContextVar[InboundMessage | None] = ContextVar(
    "tool_turn_origin", default=None
)


def set_tool_origin(message: InboundMessage) -> None:
    """Capture real inbound routing before tools run, including channel topic data."""
    _ = _origin.set(replace(message, metadata=deepcopy(message.metadata), media=[]))


def current_tool_origin() -> InboundMessage:
    """Return a copied host origin; models and public tools cannot set this value."""
    origin = _origin.get()
    if origin is None:
        raise ValueError("后台任务缺少真实入站身份")
    return replace(origin, metadata=deepcopy(origin.metadata), media=[])
