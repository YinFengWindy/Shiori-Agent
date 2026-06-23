from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BridgeError:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BridgeResponse:
    id: str
    type: str
    method: str
    payload: dict[str, Any] = field(default_factory=dict)
    error: BridgeError | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "method": self.method,
            "payload": self.payload,
            "error": self.error.to_dict() if self.error else None,
        }


@dataclass
class BridgeEvent:
    id: str
    type: str
    method: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
