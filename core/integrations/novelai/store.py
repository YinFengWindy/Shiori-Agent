from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from core.integrations.novelai.models import GeneratedImageRecord


class NovelAIStore:
    """Persist generated images and metadata under private_runtime."""

    def __init__(self, workspace: Path) -> None:
        self._root = workspace / "private_runtime" / "novelai"
        self._outputs_root = self._root / "outputs"
        self._records_path = self._root / "records.jsonl"
        self._outputs_root.mkdir(parents=True, exist_ok=True)

    def new_record_id(self) -> str:
        """Create a stable record identifier for a new generation."""

        return uuid.uuid4().hex[:16]

    def build_record_dir(self, *, created_at: datetime, record_id: str) -> Path:
        """Resolve the record output directory for the given timestamp."""

        target = self._outputs_root / created_at.strftime("%Y-%m-%d") / record_id
        target.mkdir(parents=True, exist_ok=True)
        return target

    def write_bytes(self, path: Path, content: bytes) -> None:
        """Write a binary asset to disk."""

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def write_json(self, path: Path, payload: dict[str, Any]) -> None:
        """Write JSON to disk using UTF-8 encoding."""

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def append_record(self, record: GeneratedImageRecord) -> None:
        """Append a generated-image record to the index file."""

        self._records_path.parent.mkdir(parents=True, exist_ok=True)
        with self._records_path.open("a", encoding="utf-8") as fh:
            _ = fh.write(
                json.dumps(asdict(record), ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )
