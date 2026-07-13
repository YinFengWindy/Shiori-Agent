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
        self._workspace = workspace
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

    def list_records(
        self,
        *,
        limit: int = 20,
        role_id: str = "",
    ) -> list[dict[str, Any]]:
        """Load recent generation records from the local JSONL index."""

        if limit <= 0 or not self._records_path.exists():
            return []
        clean_role_id = role_id.strip()
        items: list[dict[str, Any]] = []
        for line in self._records_path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                continue
            if clean_role_id and str(payload.get("role_id") or "").strip() != clean_role_id:
                continue
            payload["base_image_path"] = self._resolve_legacy_path(
                payload.get("base_image_path")
            )
            raw_output_paths = payload.get("output_paths")
            if isinstance(raw_output_paths, list):
                payload["output_paths"] = [
                    self._resolve_legacy_path(path) for path in raw_output_paths
                ]
            items.append(payload)
        items.sort(
            key=lambda item: str(item.get("created_at") or ""),
            reverse=True,
        )
        return items[:limit]

    def _resolve_legacy_path(self, value: object) -> str:
        """Resolve an existing legacy .akashic asset under the current workspace."""

        raw_path = str(value or "").strip()
        if not raw_path or self._workspace.parent.name != ".shiori":
            return raw_path

        legacy_root = (
            self._workspace.parent.parent
            / ".akashic"
            / "workspace"
            / "private_runtime"
            / "novelai"
        )
        try:
            relative_path = Path(raw_path).relative_to(legacy_root)
        except ValueError:
            return raw_path

        current_path = self._root / relative_path
        return str(current_path) if current_path.is_file() else raw_path
