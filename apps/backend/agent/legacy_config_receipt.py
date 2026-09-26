"""Opaque receipts for plugin-private copies of legacy host configuration."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def legacy_config_digest(values: dict[str, Any]) -> str:
    """Fingerprint resolved source values without persisting their secrets."""
    canonical = json.dumps(values, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
