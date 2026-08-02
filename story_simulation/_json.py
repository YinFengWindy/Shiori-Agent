"""JSON helpers kept local so Story does not import the retired World domain."""

from __future__ import annotations

import json
from typing import Any


def dump(value: Any) -> str:
    """Serialize durable Story payloads deterministically."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load(value: str, default: Any) -> Any:
    """Deserialize a durable payload and preserve a caller-provided default."""

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default
