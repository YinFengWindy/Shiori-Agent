from __future__ import annotations

import json
from typing import Any

try:
    import json_repair
except ImportError:  # pragma: no cover - test bootstrap may stub the module
    json_repair = None


def strip_json_fence(text: str) -> str:
    payload = (text or "").strip()
    if payload.startswith("```"):
        payload = payload.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return payload


def load_json_object_loose(text: str) -> dict[str, Any] | None:
    payload = strip_json_fence(text)
    data = _load_json_loose(payload)
    if isinstance(data, dict):
        return data
    return None


def load_json_array_loose(text: str) -> list[Any] | None:
    payload = strip_json_fence(text)
    data = _load_json_loose(payload)
    if isinstance(data, list):
        return data
    return None


def _load_json_loose(payload: str) -> Any:
    if not payload:
        return None
    try:
        if json_repair is not None:
            loads = getattr(json_repair, "loads", None)
            if callable(loads):
                return loads(payload)
            repair_json = getattr(json_repair, "repair_json", None)
            if callable(repair_json):
                repaired = repair_json(payload)
                if isinstance(repaired, (dict, list)):
                    return repaired
                if isinstance(repaired, str):
                    payload = repaired
        return json.loads(payload)
    except Exception:
        return None
