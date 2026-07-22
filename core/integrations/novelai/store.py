from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from core.common.workspace import resolve_legacy_workspace_file
from core.integrations.novelai.models import (
    GeneratedImageRecord,
    NovelAIGenerationSource,
    NovelAIMode,
)


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

        if limit <= 0:
            return []
        clean_role_id = role_id.strip()
        items: list[dict[str, Any]] = []
        for payload in self._read_record_payloads():
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

    def find_generation_source_by_output_path(
        self,
        output_path: str,
    ) -> NovelAIGenerationSource | None:
        """Load the persisted record and exact request snapshot for one output path."""

        target_path = self._canonical_path(output_path)
        if not target_path:
            return None
        for payload in reversed(self._read_record_payloads()):
            raw_output_paths = payload.get("output_paths")
            if not isinstance(raw_output_paths, list):
                continue
            for raw_output_path in raw_output_paths:
                resolved_output_path = self._resolve_legacy_path(raw_output_path)
                if self._canonical_path(resolved_output_path) != target_path:
                    continue
                request_path = Path(resolved_output_path).parent / "request.json"
                if not request_path.is_file():
                    raise ValueError(
                        f"NovelAI 原始请求快照不存在: {request_path}"
                    )
                request_payload = json.loads(request_path.read_text(encoding="utf-8"))
                if not isinstance(request_payload, dict):
                    raise ValueError("NovelAI 原始请求快照格式非法")
                parameters = request_payload.get("parameters")
                if not isinstance(parameters, dict):
                    raise ValueError("NovelAI 原始请求快照缺少 parameters")
                return NovelAIGenerationSource(
                    record=self._parse_record(payload),
                    output_path=resolved_output_path,
                    request_payload=request_payload,
                )
        return None

    def _read_record_payloads(self) -> list[dict[str, Any]]:
        if not self._records_path.exists():
            return []
        items: list[dict[str, Any]] = []
        for line in self._records_path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw:
                continue
            payload = json.loads(raw)
            if isinstance(payload, dict):
                items.append(payload)
        return items

    def _parse_record(self, payload: dict[str, Any]) -> GeneratedImageRecord:
        mode = str(payload.get("mode") or "").strip()
        if mode not in {"txt2img", "img2img"}:
            raise ValueError(f"NovelAI 记录包含非法 mode: {mode}")
        raw_output_paths = payload.get("output_paths")
        if not isinstance(raw_output_paths, list) or not raw_output_paths:
            raise ValueError("NovelAI 记录缺少 output_paths")
        raw_role_asset_paths = payload.get("role_asset_paths")
        role_asset_paths = (
            [self._resolve_legacy_path(path) for path in raw_role_asset_paths]
            if isinstance(raw_role_asset_paths, list)
            else []
        )
        return GeneratedImageRecord(
            id=str(payload.get("id") or ""),
            created_at=str(payload.get("created_at") or ""),
            role_id=str(payload.get("role_id") or ""),
            session_key=str(payload.get("session_key") or ""),
            mode=cast(NovelAIMode, mode),
            prompt=str(payload.get("prompt") or ""),
            negative_prompt=str(payload.get("negative_prompt") or ""),
            model=str(payload.get("model") or ""),
            sampler=str(payload.get("sampler") or ""),
            steps=int(payload.get("steps") or 0),
            seed=(int(payload["seed"]) if payload.get("seed") is not None else None),
            width=int(payload.get("width") or 0),
            height=int(payload.get("height") or 0),
            base_image_path=self._resolve_legacy_path(payload.get("base_image_path")),
            output_paths=[
                self._resolve_legacy_path(path) for path in raw_output_paths
            ],
            wrote_back_to_role=bool(payload.get("wrote_back_to_role")),
            role_asset_paths=role_asset_paths,
        )

    def _canonical_path(self, value: object) -> str:
        clean_value = str(value or "").strip()
        if not clean_value:
            return ""
        path = Path(clean_value)
        if not path.is_absolute():
            path = self._workspace / path
        return os.path.normcase(os.path.abspath(os.path.normpath(str(path))))

    def _resolve_legacy_path(self, value: object) -> str:
        """Resolve an existing legacy .akashic asset under the current workspace."""

        return resolve_legacy_workspace_file(self._workspace, value)
