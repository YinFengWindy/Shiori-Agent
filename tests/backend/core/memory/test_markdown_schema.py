from pathlib import Path

from core.memory.markdown_schema import (
    DOCUMENT_DEFAULTS,
    ensure_memory_documents,
    normalize_memory_document,
    pending_body,
    replace_memory_section,
)


def test_new_role_documents_use_canonical_schema(tmp_path: Path) -> None:
    ensure_memory_documents(tmp_path)

    for filename, default in DOCUMENT_DEFAULTS.items():
        assert (tmp_path / filename).read_text(encoding="utf-8") == default


def test_existing_memory_documents_are_not_rewritten(tmp_path: Path) -> None:
    original = "# 自定义标题\n\n保留用户编辑。\n"
    (tmp_path / "SELF.md").write_text(original, encoding="utf-8")

    ensure_memory_documents(tmp_path)

    assert (tmp_path / "SELF.md").read_text(encoding="utf-8") == original


def test_memory_document_write_normalizes_line_endings_only() -> None:
    content = "# 最近发生的事\r\n\r\n## 最近聊过的事\r\n- 当前用户说过的话"
    assert normalize_memory_document("RECENT_CONTEXT.md", content) == (
        "# 最近发生的事\n\n## 最近聊过的事\n- 当前用户说过的话\n"
    )


def test_pending_body_removes_only_the_document_title() -> None:
    pending = "# 待整理的记忆\n- [preference] 保持简洁\n"
    assert pending_body(pending) == "- [preference] 保持简洁"


def test_replace_memory_section_appends_missing_section_without_rewriting_custom_text(
    tmp_path: Path,
) -> None:
    path = tmp_path / "SELF.md"
    original = "# 自定义标题\n\n保留用户编辑。\n"
    path.write_text(original, encoding="utf-8")

    replace_memory_section(path, "## 我的性格与形象", "- 新增内容")

    assert path.read_text(encoding="utf-8") == (
        "# 自定义标题\n\n保留用户编辑。\n\n"
        "## 我的性格与形象\n\n- 新增内容\n"
    )
