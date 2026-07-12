from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

_MAX_MATCHES = 5
_ALLOWED_RATINGS = {"general", "sensitive", "adult"}


@dataclass(frozen=True)
class PromptTagEntry:
    """One editable prompt-tag knowledge-base entry."""

    id: str
    name: str
    enabled: bool
    category: str
    match_terms: list[str]
    positive_tags: list[str]
    negative_tags: list[str]
    rating: str = "general"
    image_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON representation used by the desktop bridge."""

        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "category": self.category,
            "match_terms": list(self.match_terms),
            "positive_tags": list(self.positive_tags),
            "negative_tags": list(self.negative_tags),
            "rating": self.rating,
            "image_path": self.image_path,
        }


@dataclass(frozen=True)
class PromptTagExpansion:
    """Resolved tags appended to a generation prompt."""

    prompt: str
    negative_prompt: str
    matched_entry_ids: list[str]


class PromptTagStore:
    """Persist and validate the workspace-owned prompt-tag catalog."""

    def __init__(self, workspace: Path) -> None:
        self._path = workspace / "private_runtime" / "novelai" / "prompt_tags.json"

    def list_entries(self) -> list[PromptTagEntry]:
        """Load all catalog entries in stable name order."""

        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("prompt_tags.json 顶层必须是数组")
        items = cast(list[Any], raw)
        entries = [self._parse_entry(item) for item in items]
        ids = [entry.id for entry in entries]
        if len(ids) != len(set(ids)):
            raise ValueError("提示词 tag ID 不能重复")
        entries.sort(key=lambda item: (item.category.casefold(), item.name.casefold()))
        return entries

    def upsert(self, payload: dict[str, Any]) -> PromptTagEntry:
        """Validate and insert or replace one catalog entry."""

        entry = self._parse_entry(payload)
        entries = [item for item in self.list_entries() if item.id != entry.id]
        entries.append(entry)
        self._write(entries)
        return entry

    def delete(self, entry_id: str) -> None:
        """Delete one catalog entry, failing when it does not exist."""

        clean_id = entry_id.strip()
        entries = self.list_entries()
        next_entries = [item for item in entries if item.id != clean_id]
        if len(next_entries) == len(entries):
            raise KeyError(f"提示词 tag 不存在: {clean_id}")
        self._write(next_entries)

    def expand(
        self,
        prompt: str,
        negative_prompt: str,
        *,
        allow_adult: bool,
    ) -> PromptTagExpansion:
        """Retrieve matching tags deterministically and merge them into prompts."""

        query = prompt.casefold()
        ranked: list[tuple[int, PromptTagEntry]] = []
        for entry in self.list_entries():
            if not entry.enabled or (entry.rating == "adult" and not allow_adult):
                continue
            score = sum(1 for term in entry.match_terms if term.casefold() in query)
            if score:
                ranked.append((score, entry))
        ranked.sort(key=lambda item: (-item[0], item[1].name.casefold()))
        selected = [entry for _, entry in ranked[:_MAX_MATCHES]]
        positive = _merge_tags(
            prompt, [tag for entry in selected for tag in entry.positive_tags]
        )
        negative = _merge_tags(
            negative_prompt,
            [tag for entry in selected for tag in entry.negative_tags],
        )
        return PromptTagExpansion(
            prompt=positive,
            negative_prompt=negative,
            matched_entry_ids=[entry.id for entry in selected],
        )

    def _parse_entry(self, raw: object) -> PromptTagEntry:
        if not isinstance(raw, dict):
            raise ValueError("提示词 tag 条目必须是对象")
        payload = cast(dict[str, Any], raw)
        entry_id = _required_text(payload, "id")
        name = _required_text(payload, "name")
        category = _required_text(payload, "category")
        rating = str(payload.get("rating") or "general").strip().casefold()
        if rating not in _ALLOWED_RATINGS:
            raise ValueError(f"提示词 tag rating 不支持: {rating}")
        return PromptTagEntry(
            id=entry_id,
            name=name,
            enabled=bool(payload.get("enabled", True)),
            category=category,
            match_terms=_text_list(payload.get("match_terms"), "match_terms"),
            positive_tags=_text_list(payload.get("positive_tags"), "positive_tags"),
            negative_tags=_text_list(
                payload.get("negative_tags"),
                "negative_tags",
                allow_empty=True,
            ),
            rating=rating,
            image_path=str(payload.get("image_path") or "").strip(),
        )

    def _write(self, entries: list[PromptTagEntry]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(
            [entry.to_dict() for entry in entries],
            ensure_ascii=False,
            indent=2,
        )
        fd, temp_name = tempfile.mkstemp(
            prefix="prompt_tags.",
            suffix=".tmp",
            dir=self._path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                _ = handle.write(content)
            _ = Path(temp_name).replace(self._path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"提示词 tag 缺少 {key}")
    return value


def _text_list(value: object, key: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"提示词 tag {key} 必须是数组")
    raw_items = cast(list[Any], value)
    items = [str(item).strip() for item in raw_items if str(item).strip()]
    if not items and not allow_empty:
        raise ValueError(f"提示词 tag {key} 不能为空")
    return list(dict.fromkeys(items))


def _merge_tags(base: str, tags: list[str]) -> str:
    parts = [part.strip() for part in base.split(",") if part.strip()]
    seen = {part.casefold() for part in parts}
    for tag in tags:
        clean = tag.strip()
        if clean and clean.casefold() not in seen:
            parts.append(clean)
            seen.add(clean.casefold())
    return ", ".join(parts)
