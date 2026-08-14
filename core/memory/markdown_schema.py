"""Canonical role-memory Markdown schemas and legacy migration helpers."""

from __future__ import annotations

import re
from pathlib import Path

DOCUMENT_DEFAULTS = {
    "SELF.md": """# 我是谁

## 我的性格与形象
- 我以自己的身份表达，并遵守角色设定中的人格、语气和边界。

## 我对你的理解
- 我只根据你明确表达或确认过的信息逐步理解你，不在缺少证据时补全画像。

## 我们的关系
- 我们的关系从真实互动中发展，不虚构共同经历。
""",
    "MEMORY.md": """# 我的长期记忆

## 关于你

## 你的偏好

## 你希望我记住的事
""",
    "HISTORY.md": "# 我们的共同经历\n",
    "RECENT_CONTEXT.md": """# 最近发生的事

## 最近聊过的事
- none

## 还在继续的事
- none

## 最近的对话
<!-- a-preview = assistant reply preview only -->
- none
""",
    "PENDING.md": "# 待整理的记忆\n",
}

DOCUMENT_SECTIONS = {
    "SELF.md": (
        "## 我的性格与形象",
        "## 我对你的理解",
        "## 我们的关系",
    ),
    "MEMORY.md": (
        "## 关于你",
        "## 你的偏好",
        "## 你希望我记住的事",
    ),
}

_HEADING_ALIASES = {
    "# 角色自我认知": "# 我是谁",
    "## 人格与形象": "## 我的性格与形象",
    "## 我对当前用户的理解": "## 我对你的理解",
    "## 我们关系的定义": "## 我们的关系",
    "# 用户长期记忆": "# 我的长期记忆",
    "## 用户事实": "## 关于你",
    "## 用户画像": "## 关于你",
    "## 用户偏好": "## 你的偏好",
    "## 用户明确要求长期记住的关键内容": "## 你希望我记住的事",
    "# Recent Context": "# 最近发生的事",
    "## Compression": "## 最近聊过的事",
    "## Ongoing Threads": "## 还在继续的事",
    "## Recent Turns": "## 最近的对话",
}

_MACHINE_LINE_PREFIXES = (
    "[user]",
    "[assistant]",
    "[a-preview]",
    "<!-- consolidation:",
    "<!-- a-preview",
)


def ensure_memory_documents(memory_dir: Path) -> None:
    """Creates and migrates every role-memory document in place."""

    memory_dir.mkdir(parents=True, exist_ok=True)
    self_path = memory_dir / "SELF.md"
    memory_path = memory_dir / "MEMORY.md"
    legacy_background = _legacy_document_body(self_path, "# 角色背景")
    legacy_relationship = _legacy_document_body(memory_path, "# 关系基线")
    for filename, default in DOCUMENT_DEFAULTS.items():
        path = memory_dir / filename
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        migrated = normalize_memory_document(filename, current)
        if not current or migrated != current:
            path.write_text(migrated, encoding="utf-8")
    if legacy_background:
        replace_memory_section(
            self_path,
            "## 我的性格与形象",
            legacy_background,
        )
    if legacy_relationship:
        relationship = re.sub(r"^来源:\s*[^\n]+\n*", "", legacy_relationship).strip()
        replace_memory_section(
            self_path,
            "## 我们的关系",
            relationship,
        )
        memory_path.write_text(DOCUMENT_DEFAULTS["MEMORY.md"], encoding="utf-8")


def normalize_memory_document(filename: str, content: str) -> str:
    """Normalizes legacy headings and role-relative prose for one document."""

    if filename not in DOCUMENT_DEFAULTS:
        raise ValueError(f"unsupported memory document: {filename}")
    text = str(content or "").replace("\r\n", "\n").strip()
    if not text:
        return DOCUMENT_DEFAULTS[filename].rstrip() + "\n"

    lines = [_HEADING_ALIASES.get(line.strip(), line) for line in text.splitlines()]
    if filename == "MEMORY.md":
        lines = _drop_section(lines, {"## 助手操作上下文", "## 运行上下文"})
    lines = _normalize_top_heading(filename, lines)
    if filename in DOCUMENT_SECTIONS:
        lines = _normalize_fixed_sections(filename, lines)
    if filename == "HISTORY.md":
        lines = _normalize_history_headings(lines)
    if filename in {"SELF.md", "MEMORY.md", "HISTORY.md", "RECENT_CONTEXT.md"}:
        lines = [_role_relative_line(line) for line in lines]
    return "\n".join(lines).strip() + "\n"


def pending_body(content: str) -> str:
    """Returns pending items without the canonical document title."""

    lines = str(content or "").splitlines()
    if lines and lines[0].strip() == "# 待整理的记忆":
        lines = lines[1:]
    return "\n".join(lines).strip()


def replace_memory_section(path: Path, heading: str, body: str) -> None:
    """Replaces one canonical SELF or MEMORY section without touching its peers."""

    filename = path.name
    sections = DOCUMENT_SECTIONS.get(filename)
    if sections is None or heading not in sections:
        raise ValueError(f"unsupported memory section: {filename} {heading}")
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = normalize_memory_document(filename, current).rstrip().splitlines()
    start = lines.index(heading)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index] in sections:
            end = index
            break
    clean_body = str(body or "").strip()
    replacement = [heading]
    if clean_body:
        replacement.extend(["", *clean_body.splitlines()])
    updated = [*lines[:start], *replacement, "", *lines[end:]]
    path.write_text("\n".join(updated).strip() + "\n", encoding="utf-8")


def _normalize_top_heading(filename: str, lines: list[str]) -> list[str]:
    expected = DOCUMENT_DEFAULTS[filename].splitlines()[0]
    if lines and lines[0].startswith("# "):
        lines[0] = expected
        return lines
    return [expected, "", *lines]


def _normalize_fixed_sections(filename: str, lines: list[str]) -> list[str]:
    sections = DOCUMENT_SECTIONS[filename]
    collected = {heading: [] for heading in sections}
    active: str | None = None
    preamble: list[str] = []
    for line in lines[1:]:
        stripped = line.strip()
        if stripped in sections:
            active = stripped
            continue
        if re.match(r"^#{1,2} ", stripped):
            active = None
            continue
        if active is not None:
            collected[active].append(line)
        elif stripped:
            preamble.append(line)
    if preamble:
        collected[sections[0]] = [*preamble, *collected[sections[0]]]
    normalized = [DOCUMENT_DEFAULTS[filename].splitlines()[0], ""]
    for heading in sections:
        normalized.append(heading)
        body = "\n".join(collected[heading]).strip()
        if body:
            normalized.extend(["", *body.splitlines()])
        normalized.append("")
    return normalized


def _normalize_history_headings(lines: list[str]) -> list[str]:
    normalized = [lines[0]]
    for line in lines[1:]:
        stripped = line.strip()
        if stripped.startswith("#"):
            label = stripped.lstrip("#").strip()
            if label:
                normalized.extend(["", f"- {label}"])
            continue
        normalized.append(line)
    return normalized


def _legacy_document_body(path: Path, heading: str) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    if not text.startswith(heading):
        return ""
    return text.removeprefix(heading).strip()


def _drop_section(lines: list[str], headings: set[str]) -> list[str]:
    kept: list[str] = []
    dropping = False
    for line in lines:
        if line.strip() in headings:
            dropping = True
            continue
        if dropping and re.match(r"^#{1,2} ", line):
            dropping = False
        if not dropping:
            kept.append(line)
    return kept


def _role_relative_line(line: str) -> str:
    stripped = line.lstrip()
    if stripped.startswith(_MACHINE_LINE_PREFIXES) or stripped.startswith("#"):
        return line
    line = line.replace("当前用户", "你")
    line = re.sub(r"(?<![\w])用户(?=[的向与在是曾会希明偏喜需]|$)", "你", line)
    line = re.sub(r"(?<![\w])助手(?=[的向与在是曾会希明]|$)", "我", line)
    return line
