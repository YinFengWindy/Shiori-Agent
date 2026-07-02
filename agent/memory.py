import logging
import re
import sqlite3
import threading
from pathlib import Path

from infra.persistence.json_store import atomic_save_json, load_json
from utils.helpers import ensure_dir

logger = logging.getLogger(__name__)

_CONSOLIDATION_MARKER_PREFIX = "<!-- consolidation:"
_CONSOLIDATION_MARKER_SUFFIX = " -->"
_CONSOLIDATION_TAIL_BYTES = 1024 * 1024
_JOURNAL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MEMBER_PENDING_VERSION = 1
DEFAULT_SELF_MD = """# 角色自我认知

## 人格与形象
- 我以当前角色的身份与用户互动，保持稳定的人格、语气和边界。
- 我会在角色设定允许的范围内自然表达自己，不把自己写成系统底座、执行框架或抽象工具。

## 我对当前用户的理解
- 我会从长期记忆中逐步形成对当前用户的理解，不在缺少证据时编造画像。

## 我们关系的定义
- 我与当前用户的关系以透明、尊重边界和持续协作为基础。
"""


class MemoryStore:
    """Workspace-local markdown memory store.

    This class only manages a `<root>/memory/` directory relative to the
    provided workspace path. In strict role-first mode, production runtime
    access must go through `core.memory.markdown.resolve_markdown_store()`
    and bind to `roles/<role_id>/memory/`.

    File layout:
    - MEMORY.md
    - Member.md
    - SELF.md
    - PENDING.md
    - Member.pending.json
    - HISTORY.md
    - RECENT_CONTEXT.md
    - journal/
    """

    def __init__(self, workspace: Path):
        self.memory_dir = ensure_dir(workspace / "memory")
        self.journal_dir = ensure_dir(self.memory_dir / "journal")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.member_file = self.memory_dir / "Member.md"
        self.history_file = self.memory_dir / "HISTORY.md"
        self.recent_context_file = self.memory_dir / "RECENT_CONTEXT.md"
        self.pending_file = self.memory_dir / "PENDING.md"
        self.member_pending_file = self.memory_dir / "Member.pending.json"
        self.self_file = self.memory_dir / "SELF.md"
        self._consolidation_db = self.memory_dir / "consolidation_writes.db"
        self._consolidation_lock = threading.Lock()
        # 确保 PENDING.md 始终存在，避免首次运行时找不到文件
        if not self.pending_file.exists():
            self.pending_file.touch()
        self._init_consolidation_db()
        # 崩溃恢复：启动时若遗留 snapshot，回滚合并
        self._recover_pending_snapshot()
        self._recover_member_pending_snapshot()

    # ── long-term memory (MEMORY.md) ─────────────────────────────

    def read_long_term(self) -> str:
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        self.memory_file.write_text(content, encoding="utf-8")

    def read_member_memory(self) -> str:
        if self.member_file.exists():
            return self.member_file.read_text(encoding="utf-8")
        return ""

    def write_member_memory(self, content: str) -> None:
        self.member_file.write_text(content, encoding="utf-8")

    def read_member_memory_section(self, member_key: str) -> str:
        text = self.read_member_memory()
        clean_member_key = str(member_key or "").strip()
        if not text or not clean_member_key:
            return ""
        target_header = f"## {clean_member_key}"
        lines = text.splitlines()
        section_lines: list[str] = []
        in_section = False
        for line in lines:
            if line.startswith("## "):
                if in_section:
                    break
                if line.strip() == target_header:
                    in_section = True
                    section_lines.append(line)
                continue
            if in_section:
                section_lines.append(line)
        return "\n".join(section_lines).strip()

    def append_history(self, entry: str) -> None:
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def append_history_once(
        self,
        entry: str,
        *,
        source_ref: str,
        kind: str = "history_entry",
    ) -> bool:
        """按 source_ref 幂等追加 HISTORY，避免重启后重复 consolidation。"""
        text = (entry or "").strip()
        if not text:
            return False
        return self._append_once_with_index(
            target_file=self.history_file,
            text=text,
            source_ref=source_ref,
            kind=kind,
            trailing_blank_line=True,
        )

    def read_history(self, max_chars: int = 0) -> str:
        """读取 HISTORY.md，并过滤 consolidation 标记行。"""
        if not self.history_file.exists():
            return ""
        text = self.history_file.read_text(encoding="utf-8")
        text = self._strip_consolidation_markers(text)
        if max_chars > 0 and len(text) > max_chars:
            return text[-max_chars:]
        return text

    # ── journal/ (per-day event timeline) ───────────────────────────

    def append_journal(
        self,
        date_str: str,
        entry: str,
        *,
        source_ref: str = "",
        kind: str = "journal",
    ) -> bool:
        date_str = date_str.strip()
        text = (entry or "").strip()
        if not _JOURNAL_DATE_RE.fullmatch(date_str) or not text:
            return False
        journal_file = self.journal_dir / f"{date_str}.md"
        if not journal_file.exists():
            journal_file.write_text(f"# {date_str}\n\n", encoding="utf-8")
        if source_ref:
            return self._append_once_with_index(
                target_file=journal_file,
                text=text,
                source_ref=source_ref,
                kind=kind,
                trailing_blank_line=True,
            )
        with open(journal_file, "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n\n")
        return True

    # ── RECENT_CONTEXT.md (compacted recent context) ──────────────

    def read_recent_context(self) -> str:
        if self.recent_context_file.exists():
            return self.recent_context_file.read_text(encoding="utf-8")
        return ""

    def write_recent_context(self, content: str) -> None:
        self.recent_context_file.write_text(content, encoding="utf-8")

    # ── SELF.md (role self-model) ──────────────────────────────

    def read_self(self) -> str:
        if self.self_file.exists():
            return self.self_file.read_text(encoding="utf-8")
        return ""

    def write_self(self, content: str) -> None:
        self.self_file.write_text(content, encoding="utf-8")

    # ── pending facts (conversation → optimizer buffer) ───────────

    def read_pending(self) -> str:
        if self.pending_file.exists():
            return self._strip_consolidation_markers(
                self.pending_file.read_text(encoding="utf-8")
            )
        return ""

    def append_pending(self, facts: str) -> None:
        """追加对话中提取的增量事实片段，不触碰 MEMORY.md。"""
        if not facts or not facts.strip():
            return
        with open(self.pending_file, "a", encoding="utf-8") as f:
            f.write(facts.rstrip() + "\n")

    def append_pending_once(
        self,
        facts: str,
        *,
        source_ref: str,
        kind: str = "pending",
    ) -> bool:
        """按 source_ref 幂等追加 PENDING，避免重启后重复 consolidation。"""
        text = (facts or "").strip()
        if not text:
            return False
        return self._append_once_with_index(
            target_file=self.pending_file,
            text=text,
            source_ref=source_ref,
            kind=kind,
            trailing_blank_line=False,
        )

    def clear_pending(self) -> None:
        """optimizer 归档后清空 PENDING.md。"""
        self.pending_file.write_text("", encoding="utf-8")

    # ── member pending facts (group member → optimizer buffer) ───────────

    @property
    def _member_snapshot_path(self) -> Path:
        return self.member_pending_file.with_name("Member.pending.snapshot.json")

    def read_member_pending(self) -> dict[str, object]:
        self._recover_member_pending_snapshot()
        return self._load_member_pending_payload(self.member_pending_file)

    def append_member_pending_entry(
        self,
        *,
        member_key: str,
        source_ref: str,
        history_entry_payloads: list[tuple[str, int]],
        pending_items: str,
    ) -> bool:
        clean_member_key = str(member_key or "").strip()
        clean_source_ref = str(source_ref or "").strip()
        normalized_history = [
            {"summary": str(summary or "").strip(), "emotional_weight": int(weight)}
            for summary, weight in history_entry_payloads
            if str(summary or "").strip()
        ]
        pending_lines = [
            line.strip()
            for line in str(pending_items or "").splitlines()
            if line.strip()
        ]
        if (
            not clean_member_key
            or not clean_source_ref
            or (not normalized_history and not pending_lines)
        ):
            return False

        self._recover_member_pending_snapshot()
        payload = self._load_member_pending_payload(self.member_pending_file)
        items = list(payload.get("items") or [])
        if any(
            isinstance(item, dict)
            and str(item.get("member_key") or "").strip() == clean_member_key
            and str(item.get("source_ref") or "").strip() == clean_source_ref
            for item in items
        ):
            return False
        items.append(
            {
                "member_key": clean_member_key,
                "source_ref": clean_source_ref,
                "history_entries": normalized_history,
                "pending_items": pending_lines,
            }
        )
        self._save_member_pending_payload(
            self.member_pending_file,
            {"version": _MEMBER_PENDING_VERSION, "items": items},
        )
        return True

    def snapshot_member_pending(self) -> dict[str, object]:
        self._recover_member_pending_snapshot()
        payload = self._load_member_pending_payload(self.member_pending_file)
        if not payload.get("items"):
            return self._empty_member_pending_payload()
        self.member_pending_file.rename(self._member_snapshot_path)
        return self._load_member_pending_payload(self._member_snapshot_path)

    def commit_member_pending_snapshot(self) -> None:
        if self._member_snapshot_path.exists():
            self._member_snapshot_path.unlink()
        if not self.member_pending_file.exists():
            self._save_member_pending_payload(
                self.member_pending_file,
                self._empty_member_pending_payload(),
            )

    def rollback_member_pending_snapshot(self) -> None:
        if not self._member_snapshot_path.exists():
            return
        snapshot_payload = self._load_member_pending_payload(self._member_snapshot_path)
        current_payload = self._load_member_pending_payload(self.member_pending_file)
        merged = self._merge_member_pending_payloads(snapshot_payload, current_payload)
        self._save_member_pending_payload(self.member_pending_file, merged)
        self._member_snapshot_path.unlink()
        logger.info("[memory] Member.pending snapshot 已回滚合并")

    def _recover_member_pending_snapshot(self) -> None:
        if self._member_snapshot_path.exists():
            logger.warning("[memory] 检测到遗留 Member.pending.snapshot.json，执行崩溃回滚")
            self.rollback_member_pending_snapshot()

    # ── 两阶段提交（供 MemoryOptimizer 使用）──────────────────────

    @property
    def _snapshot_path(self) -> Path:
        return self.pending_file.with_name("PENDING.snapshot.md")

    def snapshot_pending(self) -> str:
        """Phase-1：原子移走 PENDING.md，返回其内容。

        rename 之后 append_pending 会写入新建的 PENDING.md，
        与本次快照完全隔离，不会丢失后续增量。
        调用前会自动处理上次崩溃遗留的 snapshot。
        """
        self._recover_pending_snapshot()
        if not self.pending_file.exists() or self.pending_file.stat().st_size == 0:
            return ""
        # POSIX rename 是原子操作：rename 完成后新追加写入全新的 PENDING.md
        self.pending_file.rename(self._snapshot_path)
        return self._strip_consolidation_markers(
            self._snapshot_path.read_text(encoding="utf-8")
        )

    def commit_pending_snapshot(self) -> None:
        """Phase-2 成功：merge 已完成，删除快照。"""
        if self._snapshot_path.exists():
            self._snapshot_path.unlink()
        # 保持 PENDING.md 常驻，避免“已归档后文件消失”带来的状态歧义
        if not self.pending_file.exists():
            self.pending_file.touch()

    def rollback_pending_snapshot(self) -> None:
        """Phase-2 失败：将快照内容合并回 PENDING.md，不丢失任何数据。

        快照（较旧）在前，运行期新追加（较新）在后。
        """
        if not self._snapshot_path.exists():
            return
        snap_text = self._snapshot_path.read_text(encoding="utf-8")
        new_text = (
            self.pending_file.read_text(encoding="utf-8")
            if self.pending_file.exists()
            else ""
        )
        merged = snap_text.rstrip() + "\n" + new_text if new_text.strip() else snap_text
        self.pending_file.write_text(merged, encoding="utf-8")
        self._snapshot_path.unlink()
        logger.info("[memory] PENDING snapshot 已回滚合并")

    def _recover_pending_snapshot(self) -> None:
        """启动时或 snapshot_pending 前调用，处理上次崩溃遗留的快照。"""
        if self._snapshot_path.exists():
            logger.warning("[memory] 检测到遗留 PENDING.snapshot.md，执行崩溃回滚")
            self.rollback_pending_snapshot()

    def get_memory_context(self) -> str:
        long_term = self.read_long_term()
        return f"## Long-term Memory\n{long_term}" if long_term else ""

    @staticmethod
    def _consolidation_marker(source_ref: str, kind: str) -> str:
        src = (source_ref or "").replace("\n", " ").strip()
        kd = (kind or "").replace("\n", " ").strip()
        return f"{_CONSOLIDATION_MARKER_PREFIX}{src}:{kd}{_CONSOLIDATION_MARKER_SUFFIX}"

    @staticmethod
    def _strip_consolidation_markers(text: str) -> str:
        lines = text.splitlines()
        kept = [
            line
            for line in lines
            if not (
                line.startswith(_CONSOLIDATION_MARKER_PREFIX)
                and line.endswith(_CONSOLIDATION_MARKER_SUFFIX)
            )
        ]
        return "\n".join(kept).strip()

    def _init_consolidation_db(self) -> None:
        conn = sqlite3.connect(str(self._consolidation_db))
        try:
            conn.execute("""CREATE TABLE IF NOT EXISTS consolidation_writes (
                    source_ref TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT,
                    trailing_blank_line INTEGER NOT NULL DEFAULT 0,
                    done_at TEXT NOT NULL,
                    PRIMARY KEY (source_ref, kind)
                )""")
            cols = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(consolidation_writes)"
                ).fetchall()
            }
            if "payload" not in cols:
                conn.execute("ALTER TABLE consolidation_writes ADD COLUMN payload TEXT")
            if "trailing_blank_line" not in cols:
                conn.execute(
                    "ALTER TABLE consolidation_writes ADD COLUMN trailing_blank_line INTEGER NOT NULL DEFAULT 0"
                )
            conn.commit()
        finally:
            conn.close()

    def _append_once_with_index(
        self,
        *,
        target_file: Path,
        text: str,
        source_ref: str,
        kind: str,
        trailing_blank_line: bool,
    ) -> bool:
        marker = self._consolidation_marker(source_ref, kind)
        src = (source_ref or "").strip()
        kd = (kind or "").strip()
        if not src or not kd or not text:
            return False

        with self._consolidation_lock:
            conn = sqlite3.connect(str(self._consolidation_db), timeout=30.0)
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT payload, trailing_blank_line FROM consolidation_writes WHERE source_ref=? AND kind=?",
                    (src, kd),
                ).fetchone()
                if row is not None:
                    existing_payload = row[0] or ""
                    existing_trailing = bool(int(row[1] or 0))
                    if not self._file_contains_marker(target_file, marker):
                        if existing_payload:
                            with open(target_file, "a", encoding="utf-8") as f:
                                f.write(marker + "\n")
                                f.write(existing_payload.rstrip() + "\n")
                                if existing_trailing:
                                    f.write("\n")
                    conn.execute("COMMIT")
                    return False

                # 恢复路径：若历史崩溃发生在“文件已写，索引未写”，用尾部扫描补索引并跳过重复写。
                if self._tail_contains_marker(target_file, marker):
                    conn.execute(
                        "INSERT OR REPLACE INTO consolidation_writes(source_ref, kind, payload, trailing_blank_line, done_at) VALUES (?, ?, ?, ?, datetime('now'))",
                        (src, kd, text, 1 if trailing_blank_line else 0),
                    )
                    conn.execute("COMMIT")
                    return False

                with open(target_file, "a", encoding="utf-8") as f:
                    f.write(marker + "\n")
                    f.write(text.rstrip() + "\n")
                    if trailing_blank_line:
                        f.write("\n")

                conn.execute(
                    "INSERT OR REPLACE INTO consolidation_writes(source_ref, kind, payload, trailing_blank_line, done_at) VALUES (?, ?, ?, ?, datetime('now'))",
                    (src, kd, text, 1 if trailing_blank_line else 0),
                )
                conn.execute("COMMIT")
                return True
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
            finally:
                conn.close()

    @staticmethod
    def _tail_contains_marker(path: Path, marker: str) -> bool:
        if not path.exists():
            return False
        try:
            with open(path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                take = min(size, _CONSOLIDATION_TAIL_BYTES)
                if take <= 0:
                    return False
                f.seek(size - take)
                tail = f.read(take).decode("utf-8", errors="ignore")
                return marker in tail
        except Exception:
            return False

    @staticmethod
    def _empty_member_pending_payload() -> dict[str, object]:
        return {"version": _MEMBER_PENDING_VERSION, "items": []}

    def _load_member_pending_payload(self, path: Path) -> dict[str, object]:
        payload = load_json(
            path,
            default=self._empty_member_pending_payload(),
            domain="member_pending",
        )
        if not isinstance(payload, dict):
            return self._empty_member_pending_payload()
        version = int(payload.get("version") or _MEMBER_PENDING_VERSION)
        raw_items = payload.get("items")
        items: list[dict[str, object]] = []
        if isinstance(raw_items, list):
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                member_key = str(item.get("member_key") or "").strip()
                source_ref = str(item.get("source_ref") or "").strip()
                if not member_key or not source_ref:
                    continue
                history_entries: list[dict[str, object]] = []
                for entry in item.get("history_entries") or []:
                    if not isinstance(entry, dict):
                        continue
                    summary = str(entry.get("summary") or "").strip()
                    if not summary:
                        continue
                    try:
                        emotional_weight = int(entry.get("emotional_weight") or 0)
                    except (TypeError, ValueError):
                        emotional_weight = 0
                    history_entries.append(
                        {
                            "summary": summary,
                            "emotional_weight": emotional_weight,
                        }
                    )
                pending_items = [
                    str(line).strip()
                    for line in (item.get("pending_items") or [])
                    if str(line).strip()
                ]
                items.append(
                    {
                        "member_key": member_key,
                        "source_ref": source_ref,
                        "history_entries": history_entries,
                        "pending_items": pending_items,
                    }
                )
        return {"version": version, "items": items}

    def _save_member_pending_payload(self, path: Path, payload: dict[str, object]) -> None:
        atomic_save_json(
            path,
            payload,
            domain="member_pending",
        )

    def _merge_member_pending_payloads(
        self,
        older: dict[str, object],
        newer: dict[str, object],
    ) -> dict[str, object]:
        merged_items: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for payload in (older, newer):
            for item in payload.get("items") or []:
                if not isinstance(item, dict):
                    continue
                key = (
                    str(item.get("member_key") or "").strip(),
                    str(item.get("source_ref") or "").strip(),
                )
                if not key[0] or not key[1] or key in seen:
                    continue
                seen.add(key)
                merged_items.append(item)
        return {"version": _MEMBER_PENDING_VERSION, "items": merged_items}

    @staticmethod
    def _file_contains_marker(path: Path, marker: str) -> bool:
        if not path.exists():
            return False
        needle = marker.encode("utf-8")
        if not needle:
            return False
        carry = b""
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    data = carry + chunk
                    if needle in data:
                        return True
                    if len(needle) > 1:
                        carry = data[-(len(needle) - 1) :]
                    else:
                        carry = b""
        except Exception:
            return False
        return False
