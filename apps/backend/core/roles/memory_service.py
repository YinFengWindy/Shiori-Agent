from __future__ import annotations

from pathlib import Path
from typing import Any

from core.memory.markdown_schema import (
    ensure_memory_documents,
    replace_memory_section,
)

from .models import RoleRecord, now_iso as _now_iso, normalize_role_id
from .self_seed_state import resolve_self_seed_state, self_fingerprint


class RoleMemoryService:
    """角色独立记忆空间服务。"""

    _FILES = (
        "MEMORY.md",
        "SELF.md",
        "HISTORY.md",
        "PENDING.md",
        "RECENT_CONTEXT.md",
    )

    def __init__(self, workspace: Path) -> None:
        self._workspace = Path(workspace)

    def memory_root(self, role_id: str) -> Path:
        return self._workspace / "roles" / normalize_role_id(role_id) / "memory"

    def read_documents(self, role_id: str) -> list[dict[str, str]]:
        """Read the five role-owned documents without creating or changing them."""
        root = self.memory_root(role_id)
        documents: list[dict[str, str]] = []
        for name in self._FILES:
            path = root / name
            try:
                content = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                documents.append({"name": name, "status": "missing", "content": ""})
            except (OSError, UnicodeError) as error:
                documents.append(
                    {
                        "name": name,
                        "status": "error",
                        "content": "",
                        "error": str(error),
                    }
                )
            else:
                documents.append(
                    {
                        "name": name,
                        "status": "empty" if not content.strip() else "ready",
                        "content": content,
                    }
                )
        return documents

    def ensure_initialized(self, role: RoleRecord) -> Path:
        root = self.memory_root(role.id)
        ensure_memory_documents(root)
        return root

    def prepare_memory(self, role: RoleRecord) -> dict[str, Any]:
        """Prepares local defaults without making model calls or replacing user edits."""
        path = self.memory_root(role.id) / "SELF.md"
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        seed = resolve_self_seed_state(role, content)
        root = self.ensure_initialized(role)
        state = dict(role.memory_init_state or {})
        state["self_seed"] = seed
        state.pop("seed_self_pending", None)
        state.pop("seed_self_ready", None)
        if seed["status"] == "pending":
            state = self._prepare_defaults(role, root, state)
            state["self_seed"]["fingerprint"] = self_fingerprint(
                path.read_text(encoding="utf-8")
            )
        return state

    def _prepare_defaults(
        self,
        role: RoleRecord,
        root: Path,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        changed = False
        background = role.background.strip()
        previous_background = str(state.get("seed_background_value") or "").strip()
        if background and background != previous_background:
            self._write_stable_background(root / "SELF.md", background)
            if previous_background:
                self._append_once(
                    root / "HISTORY.md",
                    (
                        f"- [{_now_iso()}] 我的角色背景完成修订。\n"
                        f"  - 来源: user_edited\n"
                        f"  - 旧版本: {previous_background}\n"
                        f"  - 新版本: {background}\n"
                    ),
                )
            state["seed_background_ready"] = True
            state["seed_background_value"] = background
            changed = True

        if not state.get("seed_first_impression_ready"):
            impression = self._build_first_impression(role)
            state = self.update_relationship_baseline(
                role,
                content=impression,
                source="seed:first_impression",
                current_state=state,
            )
            changed = True

        if changed:
            state["last_memory_initialized_at"] = _now_iso()
        return state

    def update_relationship_baseline(
        self,
        role: RoleRecord,
        *,
        content: str,
        source: str,
        current_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_content = str(content or "").strip()
        clean_source = str(source or "").strip()
        if not clean_content:
            raise ValueError("relationship baseline 不能为空")
        if not clean_source:
            raise ValueError("relationship baseline source 不能为空")

        state = dict(current_state or role.memory_init_state or {})
        root = self.ensure_initialized(role)
        path = root / "SELF.md"
        current_value = str(state.get("relationship_baseline_value") or "").strip()
        current_source = str(state.get("relationship_baseline_source") or "").strip()
        normalized_source = "seed" if clean_source.startswith("seed") else clean_source

        if normalized_source == "system_derived" and current_source == "user_edited":
            self._append_once(
                root / "HISTORY.md",
                (
                    f"- [{_now_iso()}] 我们的关系出现新的演化建议。\n"
                    f"  - 来源: {clean_source}\n"
                    f"  - 保留当前人工基线: {current_value}\n"
                    f"  - 系统建议: {clean_content}\n"
                ),
            )
            state["relationship_revision_count"] = (
                int(state.get("relationship_revision_count") or 0) + 1
            )
            return state

        if clean_content == current_value and clean_source == current_source:
            return state

        if current_value:
            self._append_once(
                root / "HISTORY.md",
                (
                    f"- [{_now_iso()}] 我们的关系基线完成修订。\n"
                    f"  - 来源: {clean_source}\n"
                    f"  - 旧版本来源: {current_source or 'unknown'}\n"
                    f"  - 旧版本内容: {current_value}\n"
                    f"  - 新版本内容: {clean_content}\n"
                ),
            )
            if normalized_source != "seed":
                state["relationship_revision_count"] = (
                    int(state.get("relationship_revision_count") or 0) + 1
                )
        else:
            state.setdefault("relationship_revision_count", 0)

        self._write_relationship_baseline(path, clean_content, clean_source)
        state["seed_first_impression_ready"] = True
        state["relationship_baseline_value"] = clean_content
        state["relationship_baseline_source"] = clean_source
        state["last_memory_initialized_at"] = _now_iso()
        return state

    def _append_once(self, path: Path, text: str) -> None:
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if text.strip() and text.strip() not in current:
            path.write_text(
                (current.rstrip() + "\n\n" + text.strip() + "\n").lstrip(),
                encoding="utf-8",
            )

    def _write_stable_background(self, path: Path, background: str) -> None:
        replace_memory_section(path, "## 我的性格与形象", background.strip())

    def _write_relationship_baseline(
        self,
        path: Path,
        content: str,
        source: str,
    ) -> None:
        replace_memory_section(
            path,
            "## 我们的关系",
            f"来源: {source}\n\n{content.strip()}",
        )

    def _build_first_impression(self, role: RoleRecord) -> str:
        pieces = [
            "来源: seed:first_impression",
            f"角色: {role.name or role.id}",
        ]
        if role.description.strip():
            pieces.append(f"简介: {role.description.strip()}")
        pieces.append(
            "初始关系理解: 尚未与用户形成稳定互动，后续只能在此基线上增量修订。"
        )
        return "\n".join(pieces)
