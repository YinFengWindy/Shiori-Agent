from __future__ import annotations

import json
import re
from typing import Any


def extract_json_text(text: str) -> str:
    payload = (text or "").strip()
    if payload.startswith("```"):
        payload = payload.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    match = re.search(r"\{[\s\S]*\}", payload)
    if match:
        return match.group()
    return payload


def extract_json_object(text: str) -> dict[str, Any]:
    data = json.loads(extract_json_text(text))
    if not isinstance(data, dict):
        raise ValueError("json payload is not an object")
    return data
