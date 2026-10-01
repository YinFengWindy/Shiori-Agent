"""Wire response and event values used by host and plugin bridge tests."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BridgeError:
    """Structured bridge failure returned without exposing host exception objects."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes the public envelope to its transport representation."""
        return asdict(self)


@dataclass
class BridgeResponse:
    """Wire envelope for a request result or structured error."""

    id: str
    type: str
    method: str
    payload: dict[str, Any] = field(default_factory=dict)
    error: BridgeError | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes the public envelope to its transport representation."""
        return {
            "id": self.id,
            "type": self.type,
            "method": self.method,
            "payload": self.payload,
            "error": self.error.to_dict() if self.error else None,
        }


@dataclass
class BridgeEvent:
    """Wire envelope for an asynchronously emitted bridge event."""

    id: str
    type: str
    method: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes the public envelope to its transport representation."""
        return asdict(self)
